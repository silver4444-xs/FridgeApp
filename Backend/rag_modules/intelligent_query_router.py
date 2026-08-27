"""
智能查询路由器
根据查询特点自动选择最适合的检索策略：
- 传统混合检索：适合简单的信息查找
- 图RAG检索：适合复杂的关系推理和知识发现
"""

import json
import logging
from typing import List, Dict, Tuple, Any, Optional
from enum import Enum

from pydantic import BaseModel, Field
from langchain_core.documents import Document

from prompts.query_analysis import ANALYZE_QUERY
from prompts.query_rewrite import REWRITE_QUERY

logger = logging.getLogger(__name__)

# 图RAG空/占位结果的判定集合: 这些 page_content 视为"无实质内容"
_GRAPH_PLACEHOLDER_CONTENTS = frozenset({"", "空知识子图", "空路径"})

class SearchStrategy(Enum):
    """搜索策略枚举"""
    HYBRID_TRADITIONAL = "hybrid_traditional"  # 传统混合检索
    GRAPH_RAG = "graph_rag"  # 图RAG检索
    COMBINED = "combined"  # 组合策略

class QueryAnalysis(BaseModel):
    """查询分析结果 (Pydantic BaseModel，支持 langchain with_structured_output)"""
    query_complexity: float = Field(description="查询复杂度 0-1 (0=简单查找, 1=高复杂度推理)")
    relationship_intensity: float = Field(description="关系密集度 0-1 (0=单一实体, 1=复杂关系网络)")
    reasoning_required: bool = Field(description="是否需要多跳推理/因果分析/对比分析")
    entity_count: int = Field(description="查询中包含的明确实体数量")
    recommended_strategy: SearchStrategy = Field(description="推荐检索策略: hybrid_traditional/graph_rag/combined")
    confidence: float = Field(description="推荐置信度 0-1")
    reasoning: str = Field(description="推荐理由简述")


class RewrittenQuery(BaseModel):
    """查询改写结果 (Pydantic BaseModel, 支持 langchain with_structured_output)"""
    rewritten: str = Field(description="改写后的查询文本, 适合检索")
    entities: List[str] = Field(default_factory=list, description="核心实体列表")
    intent: str = Field(default="general", description="烹饪意图")
    filters: Dict[str, str] = Field(default_factory=dict, description="过滤条件")


class IntelligentQueryRouter:
    """
    智能查询路由器
    
    核心能力：
    1. 查询复杂度分析：识别简单查找 vs 复杂推理
    2. 关系密集度评估：判断是否需要图结构优势
    3. 策略自动选择：路由到最适合的检索引擎
    4. 结果质量监控：基于反馈优化路由决策
    """
    
    def __init__(self, 
                 traditional_retrieval,  # 传统混合检索模块
                 graph_rag_retrieval,    # 图RAG检索模块
                 llm_client,
                 config):
        self.traditional_retrieval = traditional_retrieval
        self.graph_rag_retrieval = graph_rag_retrieval
        self.llm_client = llm_client
        self.config = config
        
        # 路由统计
        self.route_stats = {
            "traditional_count": 0,
            "graph_rag_count": 0,
            "combined_count": 0,
            "total_queries": 0
        }
        
    def rewrite_query(self, query: str) -> RewrittenQuery:
        """将用户口语化查询改写为适合检索的形式。

        提取实体、意图和过滤条件，同时用于后续检索策略选择。
        LLM 调用失败时返回原始查询作为降级。
        """
        logger.info(f"改写查询: {query}")

        try:
            messages = REWRITE_QUERY.format_prompt(query=query)
            structured_llm = self.llm_client.with_structured_output(
                RewrittenQuery, method="function_calling"
            )
            rewritten = structured_llm.invoke(messages)
            logger.info(
                f"查询改写完成: '{query}' → '{rewritten.rewritten}' "
                f"(意图: {rewritten.intent}, 实体: {rewritten.entities})"
            )
            return rewritten

        except Exception as e:
            logger.warning(f"查询改写失败 ({e})，使用原始查询")
            return RewrittenQuery(
                rewritten=query,
                entities=[],
                intent="general",
                filters={},
            )

    def analyze_query(self, query: str) -> QueryAnalysis:
        """
        深度分析查询特征，决定最佳检索策略
        """
        logger.info(f"分析查询特征: {query}")

        # ChatPromptTemplate + with_structured_output 调用
        try:
            messages = ANALYZE_QUERY.format_prompt(query=query)
            structured_llm = self.llm_client.with_structured_output(QueryAnalysis, method="function_calling")
            analysis = structured_llm.invoke(messages)
            analysis = self._enforce_strategy_consistency(analysis)
            logger.info(f"查询分析完成: {analysis.recommended_strategy.value} (置信度: {analysis.confidence:.2f})")
            return analysis
        except Exception as e:
            logger.error(f"查询分析失败: {e}")
            # 降级方案：基于规则的简单分析
            return self._rule_based_analysis(query)
    
    def _rule_based_analysis(self, query: str) -> QueryAnalysis:
        """基于规则的降级分析"""
        # 简单的规则判断
        complexity_keywords = ["为什么", "如何", "关系", "影响", "原因", "比较", "区别"]
        relation_keywords = ["配", "搭配", "组合", "相关", "联系", "连接"]
        
        complexity = sum(1 for kw in complexity_keywords if kw in query) / len(complexity_keywords)
        relation_intensity = sum(1 for kw in relation_keywords if kw in query) / len(relation_keywords)
        
        if complexity > 0.3 or relation_intensity > 0.3:
            strategy = SearchStrategy.GRAPH_RAG
        else:
            strategy = SearchStrategy.HYBRID_TRADITIONAL
            
        return QueryAnalysis(
            query_complexity=complexity,
            relationship_intensity=relation_intensity,
            reasoning_required=complexity > 0.3,
            entity_count=len(query.split()),
            recommended_strategy=strategy,
            confidence=0.6,
            reasoning="基于规则的简单分析"
        )

    def _enforce_strategy_consistency(self, analysis: QueryAnalysis) -> QueryAnalysis:
        """修正 LLM 策略与自报特征矛盾 (P1 路由偏斜兜底)。

        根因: ANALYZE_QUERY 原 prompt 缺策略选择规则, LLM 保守地把 80%+ 查询
        判为 hybrid_traditional, 导致关系/推理查询拿不到图推理结果。
        此处用确定性规则兜底: 凡自报需要推理或复杂度/关系密度达阈值者,
        不得停留在 hybrid_traditional。返回新对象, 不原地修改。
        """
        need_graph = (
            analysis.reasoning_required
            or analysis.query_complexity >= 0.6
            or analysis.relationship_intensity >= 0.6
        )
        if not need_graph or analysis.recommended_strategy != SearchStrategy.HYBRID_TRADITIONAL:
            return analysis

        if analysis.query_complexity >= 0.6 and analysis.relationship_intensity >= 0.6:
            new_strategy = SearchStrategy.COMBINED
        else:
            new_strategy = SearchStrategy.GRAPH_RAG

        logger.info(
            f"策略一致性修正: hybrid_traditional → {new_strategy.value} "
            f"(reasoning_required={analysis.reasoning_required}, "
            f"complexity={analysis.query_complexity:.2f}, "
            f"relation={analysis.relationship_intensity:.2f})"
        )
        return analysis.model_copy(update={"recommended_strategy": new_strategy})

    def route_query(self, query: str, top_k: int = 5,
                    enable_rewrite: bool = True,
                    enable_rerank: bool = True) -> Tuple[List[Document], QueryAnalysis, Optional[RewrittenQuery]]:
        """
        智能路由查询到最适合的检索引擎。

        Args:
            query: 用户原始查询
            top_k: 返回文档数
            enable_rewrite: 是否启用查询改写 (默认 True)
            enable_rerank: 是否启用 Jina Reranker 精排 (默认 True)

        Returns:
            (documents, analysis, rewritten_query) 三元组
        """
        logger.info(f"开始智能路由: {query}")

        # 0. 查询改写 (P0-2.2: 口语→检索优化)
        rewritten = None
        search_query = query
        if enable_rewrite:
            rewritten = self.rewrite_query(query)
            search_query = rewritten.rewritten

        # 1. 分析查询特征 (使用改写后的查询)
        analysis = self.analyze_query(search_query)

        # 2. graph_rag 路由兜底 (P0): 图索引未命中查询实体时降级为 hybrid
        strategy = analysis.recommended_strategy
        if strategy == SearchStrategy.GRAPH_RAG and not self._graph_can_answer(
            rewritten.entities if rewritten else []
        ):
            logger.warning(
                f"图索引未命中实体，graph_rag → hybrid_traditional 兜底: '{search_query}'"
            )
            strategy = SearchStrategy.HYBRID_TRADITIONAL
            analysis = analysis.model_copy(update={"recommended_strategy": strategy})

        # 3. 更新统计
        self._update_route_stats(strategy)

        # 4. 根据策略执行检索
        documents = []

        # 精排使用原始查询 (保留用户原始意图)
        rerank_query = query

        try:
            if strategy == SearchStrategy.HYBRID_TRADITIONAL:
                logger.info("使用传统混合检索")
                documents = self.traditional_retrieval.hybrid_search_with_rerank(
                    search_query, top_k,
                    enable_rerank=enable_rerank, rerank_query=rerank_query,
                )

            elif strategy == SearchStrategy.GRAPH_RAG:
                logger.info("🕸️ 使用图RAG检索")
                documents = self.graph_rag_retrieval.graph_rag_search(search_query, top_k)
                # 图RAG空/占位结果兜底 (P0): 回退传统混合检索
                if not self._has_substantive_results(documents):
                    logger.warning(
                        f"图RAG返回空/占位结果，回退 hybrid_traditional: '{search_query}'"
                    )
                    documents = self.traditional_retrieval.hybrid_search_with_rerank(
                        search_query, top_k,
                        enable_rerank=enable_rerank, rerank_query=rerank_query,
                    )
                elif enable_rerank:
                    from .reranker import rerank_with_jina
                    documents = rerank_with_jina(
                        rerank_query, documents, top_k=min(top_k, len(documents))
                    )

            elif strategy == SearchStrategy.COMBINED:
                logger.info("🔄 使用组合检索策略")
                documents = self._combined_search(search_query, top_k,
                                                   enable_rerank=enable_rerank,
                                                   rerank_query=rerank_query)

            # 4. 结果后处理
            documents = self._post_process_results(documents, analysis)

            # 附加改写信息到元数据
            if rewritten:
                for doc in documents:
                    doc.metadata["rewritten_query"] = rewritten.rewritten
                    doc.metadata["query_entities"] = rewritten.entities
                    doc.metadata["query_intent"] = rewritten.intent

            logger.info(f"路由完成，返回 {len(documents)} 个结果")
            return documents, analysis, rewritten

        except Exception as e:
            logger.error(f"查询路由失败: {e}")
            # 降级到传统检索
            documents = self.traditional_retrieval.hybrid_search(search_query, top_k)
            return documents, analysis, rewritten
    
    def _combined_search(self, query: str, top_k: int,
                         enable_rerank: bool = True,
                         rerank_query: str = "") -> List[Document]:
        """组合搜索策略：结合传统检索和图RAG的优势。"""
        # 分配结果数量
        traditional_k = max(1, top_k // 2)
        graph_k = top_k - traditional_k

        # 执行两种检索
        traditional_docs = self.traditional_retrieval.hybrid_search_with_rerank(
            query, traditional_k, enable_rerank=False,  # 合并后再统一精排
        )
        graph_docs = self.graph_rag_retrieval.graph_rag_search(query, graph_k)

        # 合并和去重 (Round-robin, 图RAG优先)
        combined_docs = []
        seen_contents = set()

        max_len = max(len(traditional_docs), len(graph_docs))
        for i in range(max_len):
            if i < len(graph_docs):
                doc = graph_docs[i]
                content_hash = hash(doc.page_content[:100])
                if content_hash not in seen_contents:
                    seen_contents.add(content_hash)
                    doc.metadata["search_source"] = "graph_rag"
                    combined_docs.append(doc)

            if i < len(traditional_docs):
                doc = traditional_docs[i]
                content_hash = hash(doc.page_content[:100])
                if content_hash not in seen_contents:
                    seen_contents.add(content_hash)
                    doc.metadata["search_source"] = "traditional"
                    combined_docs.append(doc)

        # 合并后统一精排
        if enable_rerank and combined_docs:
            from .reranker import rerank_with_jina
            combined_docs = rerank_with_jina(
                rerank_query or query, combined_docs,
                top_k=min(top_k, len(combined_docs))
            )

        return combined_docs[:top_k]

    def _has_substantive_results(self, documents: List[Document]) -> bool:
        """判断图检索结果是否包含实质内容 (排除空列表与占位文档)。

        graph_rag 常返回空列表或 `空知识子图`/`空路径` 占位文档, 这些内容对
        下游生成毫无帮助, 应触发 hybrid 兜底。
        """
        if not documents:
            return False
        return any(
            (doc.page_content or "").strip() not in _GRAPH_PLACEHOLDER_CONTENTS
            for doc in documents
        )

    def _graph_can_answer(self, entities: List[str]) -> bool:
        """判断查询实体是否命中图索引，用于 graph_rag 路由兜底。

        镜像 graph_rag_search 的节点匹配规则 (`source.name CONTAINS entity`
        OR `source.nodeId = entity`): 只要任一实体能在图索引 entity_cache 中
        命中即视为图可回答。图索引为空 (Neo4j 未初始化/初始化失败) 或实体为空
        时返回 False, 避免把图里不存在的实体 (菜系/调味品/低度菜名) 送进图黑洞。

        局限: entity_cache 仅保留按 degree 排序的 top-1000 节点, 低度 Recipe
        节点可能不在缓存中而被误判为"不可回答" → 降级 hybrid, 属保守安全侧。
        """
        cache = getattr(self.graph_rag_retrieval, "entity_cache", None) or {}
        if not cache:
            return False
        entities = [e.strip() for e in (entities or []) if e and e.strip()]
        if not entities:
            return False
        for ent in entities:
            for node_id, info in cache.items():
                if not isinstance(info, dict):
                    continue
                name = info.get("name") or ""
                if (name and ent in name) or ent == node_id:
                    return True
        return False

    def _post_process_results(self, documents: List[Document], analysis: QueryAnalysis) -> List[Document]:
        """
        结果后处理：根据查询分析优化结果
        """
        for doc in documents:
            # 添加路由信息到元数据
            doc.metadata.update({
                "route_strategy": analysis.recommended_strategy.value,
                "query_complexity": analysis.query_complexity,
                "route_confidence": analysis.confidence
            })
        
        return documents
    
    def _update_route_stats(self, strategy: SearchStrategy):
        """更新路由统计"""
        self.route_stats["total_queries"] += 1
        
        if strategy == SearchStrategy.HYBRID_TRADITIONAL:
            self.route_stats["traditional_count"] += 1
        elif strategy == SearchStrategy.GRAPH_RAG:
            self.route_stats["graph_rag_count"] += 1
        elif strategy == SearchStrategy.COMBINED:
            self.route_stats["combined_count"] += 1
    
    def get_route_statistics(self) -> Dict[str, Any]:
        """获取路由统计信息"""
        total = self.route_stats["total_queries"]
        if total == 0:
            return self.route_stats
        
        return {
            **self.route_stats,
            "traditional_ratio": self.route_stats["traditional_count"] / total,
            "graph_rag_ratio": self.route_stats["graph_rag_count"] / total,
            "combined_ratio": self.route_stats["combined_count"] / total
        }
    
    def explain_routing_decision(self, query: str) -> str:
        """解释路由决策过程"""
        analysis = self.analyze_query(query)
        
        explanation = f"""
        查询路由分析报告
        
        查询：{query}
        
        特征分析：
        - 复杂度：{analysis.query_complexity:.2f} ({'简单' if analysis.query_complexity < 0.4 else '中等' if analysis.query_complexity < 0.8 else '复杂'})
        - 关系密集度：{analysis.relationship_intensity:.2f} ({'单一实体' if analysis.relationship_intensity < 0.4 else '实体关系' if analysis.relationship_intensity < 0.8 else '复杂关系网络'})
        - 推理需求：{'是' if analysis.reasoning_required else '否'}
        - 实体数量：{analysis.entity_count}
        
        推荐策略：{analysis.recommended_strategy.value}
        置信度：{analysis.confidence:.2f}
        
        决策理由：{analysis.reasoning}
        """
        
        return explanation

 