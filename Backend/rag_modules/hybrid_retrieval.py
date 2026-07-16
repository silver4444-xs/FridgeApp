"""
混合检索模块
基于双层检索范式：实体级 + 主题级检索
结合图结构检索和向量检索，使用Round-robin轮询策略
"""

import json
import logging
import re
from typing import List, Dict, Tuple, Any
from dataclasses import dataclass

from pydantic import BaseModel, Field
from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever
from neo4j import GraphDatabase
from .graph_indexing import GraphIndexingModule

from prompts.keyword_extraction import EXTRACT_QUERY_KEYWORDS

logger = logging.getLogger(__name__)

@dataclass
class RetrievalResult:
    """检索结果数据结构"""
    content: str
    node_id: str
    node_type: str
    relevance_score: float
    retrieval_level: str  # 'low' or 'high'
    metadata: Dict[str, Any]


class KeywordsResult(BaseModel):
    """关键词提取结果 (Pydantic BaseModel，支持 langchain with_structured_output)"""
    entity_keywords: List[str] = Field(description="实体级关键词：具体的食材、菜品名称、工具等有形实体，如 鸡胸肉/红烧肉/平底锅")
    topic_keywords: List[str] = Field(description="主题级关键词：抽象概念、烹饪主题、饮食风格等，如 减肥/川菜/快手菜")

class HybridRetrievalModule:
    """
    混合检索模块
    核心特点：
    1. 双层检索范式（实体级 + 主题级）
    2. 关键词提取和匹配
    3. 图结构+向量检索结合
    4. 一跳邻居扩展
    5. Round-robin轮询合并策略
    """
    
    def __init__(self, config, milvus_module, data_module, llm_client):
        self.config = config
        self.milvus_module = milvus_module
        self.data_module = data_module
        self.llm_client = llm_client
        self.driver = None
        self.bm25_retriever = None
        
        # 图索引模块
        self.graph_indexing = GraphIndexingModule(config, llm_client)
        self.graph_indexed = False
        
    def initialize(self, chunks: List[Document]):
        """初始化检索系统"""
        logger.info("初始化混合检索模块...")
        
        # 连接Neo4j
        self.driver = GraphDatabase.driver(
            self.config.neo4j_uri,
            auth=(self.config.neo4j_user, self.config.neo4j_password),
            database=self.config.neo4j_database
        )
        
        # 初始化BM25检索器
        if chunks:
            self.bm25_retriever = BM25Retriever.from_documents(chunks)
            logger.info(f"BM25检索器初始化完成，文档数量: {len(chunks)}")
        
        # 初始化图索引
        self._build_graph_index()
        
    def _build_graph_index(self):
        """构建图索引"""
        if self.graph_indexed:
            return
            
        logger.info("开始构建图索引...")
        
        try:
            # 获取图数据
            recipes = self.data_module.recipes
            ingredients = self.data_module.ingredients
            cooking_steps = self.data_module.cooking_steps
            
            # 创建实体键值对
            self.graph_indexing.create_entity_key_values(recipes, ingredients, cooking_steps)
            
            # 创建关系键值对（这里需要从Neo4j获取关系数据）
            relationships = self._extract_relationships_from_graph()
            self.graph_indexing.create_relation_key_values(relationships)
            
            # 去重优化
            self.graph_indexing.deduplicate_entities_and_relations()
            
            self.graph_indexed = True
            stats = self.graph_indexing.get_statistics()
            logger.info(f"图索引构建完成: {stats}")
            
        except Exception as e:
            logger.error(f"构建图索引失败: {e}")
            
    def _extract_relationships_from_graph(self) -> List[Tuple[str, str, str]]:
        """从Neo4j图中提取关系"""
        relationships = []
        
        try:
            with self.driver.session() as session:
                query = """
                MATCH (source)-[r]->(target)
                WHERE source.nodeId >= '200000000' OR target.nodeId >= '200000000'
                RETURN source.nodeId as source_id, type(r) as relation_type, target.nodeId as target_id
                LIMIT 1000
                """
                result = session.run(query)
                
                for record in result:
                    relationships.append((
                        record["source_id"],
                        record["relation_type"],
                        record["target_id"]
                    ))
                    
        except Exception as e:
            logger.error(f"提取图关系失败: {e}")
            
        return relationships
            
    def _keyword_match_score(self, keyword: str, target: str) -> float:
        """计算关键词与目标文本的匹配度 [0, 1]"""
        if not keyword or not target:
            return 0.0
        if keyword == target:
            return 1.0
        if keyword in target or target in keyword:
            return 0.8
        # 字符级 Jaccard 相似度
        kw_set = set(keyword)
        tgt_set = set(target)
        if not tgt_set:
            return 0.0
        return len(kw_set & tgt_set) / len(kw_set | tgt_set)

    def extract_query_keywords(self, query: str) -> Tuple[List[str], List[str]]:
        """
        提取查询关键词：实体级 + 主题级
        """

        # ChatPromptTemplate + with_structured_output 调用
        try:
            messages = EXTRACT_QUERY_KEYWORDS.format_prompt(query=query)
            structured_llm = self.llm_client.with_structured_output(KeywordsResult, method="function_calling")
            result = structured_llm.invoke(messages)
            entity_keywords = result.entity_keywords
            topic_keywords = result.topic_keywords
            logger.info(f"关键词提取完成 - 实体级: {entity_keywords}, 主题级: {topic_keywords}")
            return entity_keywords, topic_keywords
        except Exception as e:
            logger.error(f"关键词提取失败: {e}")
            # 降级方案：中文用正则提取连续汉字/英文词，英文用空格分割
            chars = re.findall(r'[一-鿿]{2,}|\w{2,}', query)
            if chars:
                return chars[:5], chars[:3]
            # 最终兜底：字符级二元组分词
            clean = re.sub(r'[^一-鿿\w]', '', query)
            bigrams = [clean[i:i+2] for i in range(0, len(clean)-1, 2)]
            return bigrams[:5], bigrams[:3]
    
    def entity_level_retrieval(self, entity_keywords: List[str], top_k: int = 10) -> List[RetrievalResult]:
        """
        实体级检索：专注于具体实体和关系
        使用图索引的键值对结构进行检索
        """
        results = []
        
        # 1. 使用图索引进行实体检索
        for keyword in entity_keywords:
            # 检索匹配的实体
            entities = self.graph_indexing.get_entities_by_key(keyword)
            
            for entity in entities:
                # 获取邻居信息
                neighbors = self._get_node_neighbors(entity.metadata["node_id"], max_neighbors=2)
                
                # 构建增强内容
                enhanced_content = entity.value_content
                if neighbors:
                    enhanced_content += f"\n相关信息: {', '.join(neighbors)}"
                
                # 基于关键词与实体名的相似度计算真实相关性分数
                entity_name = entity.entity_name
                score = self._keyword_match_score(keyword, entity_name)
                results.append(RetrievalResult(
                    content=enhanced_content,
                    node_id=entity.metadata["node_id"],
                    node_type=entity.entity_type,
                    relevance_score=score,
                    retrieval_level="entity",
                    metadata={
                        "entity_name": entity_name,
                        "entity_type": entity.entity_type,
                        "index_keys": entity.index_keys,
                        "matched_keyword": keyword
                    }
                ))
        
        # 2. 如果图索引结果不足，使用Neo4j进行补充检索
        if len(results) < top_k:
            neo4j_results = self._neo4j_entity_level_search(entity_keywords, top_k - len(results))
            results.extend(neo4j_results)
            
        # 3. 按相关性排序并返回
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"实体级检索完成，返回 {len(results)} 个结果")
        return results[:top_k]
    
    def _neo4j_entity_level_search(self, keywords: List[str], limit: int) -> List[RetrievalResult]:
        """Neo4j补充检索"""
        results = []
        
        try:
            with self.driver.session() as session:
                cypher_query = """
                UNWIND $keywords as keyword
                CALL db.index.fulltext.queryNodes('recipe_fulltext_index', keyword + '*') 
                YIELD node, score
                WHERE node:Recipe
                RETURN 
                    node.nodeId as node_id,
                    node.name as name,
                    node.description as description,
                    labels(node) as labels,
                    score
                ORDER BY score DESC
                LIMIT $limit
                """
                
                result = session.run(cypher_query, {
                    "keywords": keywords,
                    "limit": limit
                })
                
                for record in result:
                    content_parts = []
                    if record["name"]:
                        content_parts.append(f"菜品: {record['name']}")
                    if record["description"]:
                        content_parts.append(f"描述: {record['description']}")
                    
                    results.append(RetrievalResult(
                        content='\n'.join(content_parts),
                        node_id=record["node_id"],
                        node_type="Recipe",
                        relevance_score=float(record["score"]),  # 保留 Neo4j 原始全文检索分数
                        retrieval_level="entity",
                        metadata={
                            "name": record["name"],
                            "labels": record["labels"],
                            "source": "neo4j_fallback"
                        }
                    ))
                    
        except Exception as e:
            logger.error(f"Neo4j补充检索失败: {e}")
            
        return results
    
    def topic_level_retrieval(self, topic_keywords: List[str], top_k: int = 10) -> List[RetrievalResult]:
        """
        主题级检索：专注于广泛主题和概念
        使用图索引的关系键值对结构进行主题检索
        """
        results = []
        
        # 1. 使用图索引进行关系/主题检索
        for keyword in topic_keywords:
            # 检索匹配的关系
            relations = self.graph_indexing.get_relations_by_key(keyword)
            
            for relation in relations:
                # 获取相关实体信息
                source_entity = self.graph_indexing.entity_kv_store.get(relation.source_entity)
                target_entity = self.graph_indexing.entity_kv_store.get(relation.target_entity)
                
                if source_entity and target_entity:
                    # 构建丰富的主题内容
                    content_parts = [
                        f"主题: {keyword}",
                        relation.value_content,
                        f"相关菜品: {source_entity.entity_name}",
                        f"相关信息: {target_entity.entity_name}"
                    ]
                    
                    # 添加源实体的详细信息
                    if source_entity.entity_type == "Recipe":
                        newline = '\n'
                        content_parts.append(f"菜品详情: {source_entity.value_content.split(newline)[0]}")
                    
                    score = self._keyword_match_score(keyword, source_entity.entity_name)
                    results.append(RetrievalResult(
                        content='\n'.join(content_parts),
                        node_id=relation.source_entity,
                        node_type=source_entity.entity_type,
                        relevance_score=score,
                        retrieval_level="topic",
                        metadata={
                            "relation_id": relation.relation_id,
                            "relation_type": relation.relation_type,
                            "source_name": source_entity.entity_name,
                            "target_name": target_entity.entity_name,
                            "matched_keyword": keyword,
                            "index_keys": relation.index_keys
                        }
                    ))
        
        # 2. 使用实体的分类信息进行主题检索
        for keyword in topic_keywords:
            entities = self.graph_indexing.get_entities_by_key(keyword)
            for entity in entities:
                if entity.entity_type == "Recipe":
                    # 构建分类主题内容
                    content_parts = [
                        f"主题分类: {keyword}",
                        entity.value_content
                    ]
                    
                    score = self._keyword_match_score(keyword, entity.entity_name)
                    results.append(RetrievalResult(
                        content='\n'.join(content_parts),
                        node_id=entity.metadata["node_id"],
                        node_type=entity.entity_type,
                        relevance_score=score * 0.85,  # 分类匹配略低于直接名称匹配
                        retrieval_level="topic",
                        metadata={
                            "entity_name": entity.entity_name,
                            "entity_type": entity.entity_type,
                            "matched_keyword": keyword,
                            "source": "category_match"
                        }
                    ))
        
        # 3. 如果结果不足，使用Neo4j进行补充检索
        if len(results) < top_k:
            neo4j_results = self._neo4j_topic_level_search(topic_keywords, top_k - len(results))
            results.extend(neo4j_results)
            
        # 4. 按相关性排序并返回
        results.sort(key=lambda x: x.relevance_score, reverse=True)
        
        logger.info(f"主题级检索完成，返回 {len(results)} 个结果")
        return results[:top_k]
    
    def _neo4j_topic_level_search(self, keywords: List[str], limit: int) -> List[RetrievalResult]:
        """Neo4j主题级检索补充"""
        results = []
        
        try:
            with self.driver.session() as session:
                cypher_query = """
                UNWIND $keywords as keyword
                MATCH (r:Recipe)
                WHERE r.category CONTAINS keyword 
                   OR r.cuisineType CONTAINS keyword
                   OR r.tags CONTAINS keyword
                WITH r, keyword
                OPTIONAL MATCH (r)-[:REQUIRES]->(i:Ingredient)
                WITH r, keyword, collect(i.name)[0..3] as ingredients
                RETURN 
                    r.nodeId as node_id,
                    r.name as name,
                    r.category as category,
                    r.cuisineType as cuisine_type,
                    r.difficulty as difficulty,
                    ingredients,
                    keyword as matched_keyword
                ORDER BY r.difficulty ASC, r.name
                LIMIT $limit
                """
                
                result = session.run(cypher_query, {
                    "keywords": keywords,
                    "limit": limit
                })
                
                for record in result:
                    content_parts = []
                    content_parts.append(f"菜品: {record['name']}")
                    
                    if record["category"]:
                        content_parts.append(f"分类: {record['category']}")
                    if record["cuisine_type"]:
                        content_parts.append(f"菜系: {record['cuisine_type']}")
                    if record["difficulty"]:
                        content_parts.append(f"难度: {record['difficulty']}")
                    
                    if record["ingredients"]:
                        ingredients_str = ', '.join(record["ingredients"][:3])
                        content_parts.append(f"主要食材: {ingredients_str}")
                    
                    results.append(RetrievalResult(
                        content='\n'.join(content_parts),
                        node_id=record["node_id"],
                        node_type="Recipe",
                        relevance_score=0.60,  # CONTAINS 部分匹配，得分低于全文检索
                        retrieval_level="topic",
                        metadata={
                            "name": record["name"],
                            "category": record["category"],
                            "cuisine_type": record["cuisine_type"],
                            "difficulty": record["difficulty"],
                            "matched_keyword": record["matched_keyword"],
                            "source": "neo4j_fallback"
                        }
                    ))
                    
        except Exception as e:
            logger.error(f"Neo4j主题级检索失败: {e}")
            
        return results
        
    def dual_level_retrieval(self, query: str, top_k: int = 10) -> List[Document]:
        """
        双层检索：结合实体级和主题级检索
        """
        logger.info(f"开始双层检索: {query}")
        
        # 1. 提取关键词
        entity_keywords, topic_keywords = self.extract_query_keywords(query)
        
        # 2. 执行双层检索
        entity_results = self.entity_level_retrieval(entity_keywords, top_k)
        topic_results = self.topic_level_retrieval(topic_keywords, top_k)
        
        # 3. 结果合并和排序
        all_results = entity_results + topic_results
        
        # 4. 去重和重排序
        seen_nodes = set()
        unique_results = []
        
        for result in sorted(all_results, key=lambda x: x.relevance_score, reverse=True):
            if result.node_id not in seen_nodes:
                seen_nodes.add(result.node_id)
                unique_results.append(result)
        
        # 5. 转换为Document格式
        documents = []
        for result in unique_results[:top_k]:
            # 确保recipe_name字段正确设置
            recipe_name = result.metadata.get("name") or result.metadata.get("entity_name", "未知菜品")
            
            doc = Document(
                page_content=result.content,
                metadata={
                    "node_id": result.node_id,
                    "node_type": result.node_type,
                    "retrieval_level": result.retrieval_level,
                    "relevance_score": result.relevance_score,
                    "recipe_name": recipe_name,  # 确保有recipe_name字段
                    "search_type": "dual_level",  # 设置搜索类型
                    **result.metadata
                }
            )
            documents.append(doc)
            
        logger.info(f"双层检索完成，返回 {len(documents)} 个文档")
        return documents
    
    def vector_search_enhanced(self, query: str, top_k: int = 10) -> List[Document]:
        """
        增强的向量检索：结合图信息
        """
        try:
            # 使用Milvus进行向量检索
            vector_docs = self.milvus_module.similarity_search(query, k=top_k*2)
            
            # 用图信息增强结果并转换为Document对象
            enhanced_docs = []
            for result in vector_docs:
                # 从Milvus结果创建Document对象
                content = result.get("text", "")
                metadata = result.get("metadata", {})
                node_id = metadata.get("node_id")
                
                if node_id:
                    # 从图中获取邻居信息
                    neighbors = self._get_node_neighbors(node_id)
                    if neighbors:
                        # 将邻居信息添加到内容中
                        neighbor_info = f"\n相关信息: {', '.join(neighbors[:3])}"
                        content += neighbor_info
                
                # 确保recipe_name字段正确设置
                recipe_name = metadata.get("recipe_name", "未知菜品")
                
                # 调试：打印向量得分
                vector_score = result.get("score", 0.0)
                logger.debug(f"向量检索得分: {recipe_name} = {vector_score}")
                
                # 创建Document对象
                doc = Document(
                    page_content=content,
                    metadata={
                        **metadata,
                        "recipe_name": recipe_name,  # 确保有recipe_name字段
                        "score": vector_score,
                        "search_type": "vector_enhanced"
                    }
                )
                enhanced_docs.append(doc)
                
            return enhanced_docs[:top_k]
            
        except Exception as e:
            logger.error(f"增强向量检索失败: {e}")
            return []
    
    def _get_node_neighbors(self, node_id: str, max_neighbors: int = 3) -> List[str]:
        """获取节点的邻居信息"""
        try:
            with self.driver.session() as session:
                query = """
                MATCH (n {nodeId: $node_id})-[r]-(neighbor)
                RETURN neighbor.name as name
                LIMIT $limit
                """
                result = session.run(query, {"node_id": node_id, "limit": max_neighbors})
                return [record["name"] for record in result if record["name"]]
        except Exception as e:
            logger.error(f"获取邻居节点失败: {e}")
            return []
    
    def hybrid_search(self, query: str, top_k: int = 10) -> List[Document]:
        """
        混合检索：三路融合 (BM25 + 向量 + 图索引)
        加权合并: BM25 0.3, 向量 0.5, 图索引 0.2
        """
        logger.info(f"开始混合检索: {query}")

        # 1. 双层检索（实体+主题检索，来自图索引）
        dual_docs = self.dual_level_retrieval(query, top_k)

        # 2. 增强向量检索 (Milvus)
        vector_docs = self.vector_search_enhanced(query, top_k)

        # 3. BM25 关键词检索
        bm25_docs = []
        if self.bm25_retriever:
            try:
                bm25_raw = self.bm25_retriever.invoke(query)
                for rank, doc in enumerate(bm25_raw[:top_k]):
                    doc.metadata["search_method"] = "bm25"
                    doc.metadata["bm25_rank"] = rank
                    doc.metadata["final_score"] = 1.0 / (1.0 + rank)  # rank-based scoring
                    bm25_docs.append(doc)
                logger.info(f"BM25检索: {len(bm25_docs)} 个结果")
            except Exception as e:
                logger.error(f"BM25检索失败: {e}")

        # 4. 三路加权融合
        all_candidates = []

        for doc in dual_docs:
            doc.metadata["search_method"] = "dual_level"
            doc.metadata["final_score"] = doc.metadata.get("relevance_score", 0.0) * 0.2
            all_candidates.append(doc)

        for doc in vector_docs:
            doc.metadata["search_method"] = "vector_enhanced"
            vector_score = doc.metadata.get("score", 0.0)
            similarity = max(0.0, min(1.0, vector_score))
            doc.metadata["final_score"] = similarity * 0.5
            all_candidates.append(doc)

        for doc in bm25_docs:
            doc.metadata["final_score"] = doc.metadata["final_score"] * 0.3
            all_candidates.append(doc)

        # 5. doc_type 域加权: cooking_knowledge 文档在通用烹饪问题中偏低,
        #    因为图索引的关键词精确匹配天然偏向菜谱实体。给予 cooking_knowledge
        #    适度的分数补偿 (1.4x), 菜谱文档保持不变 (1.0x)。
        max_dual_score = max(
            (d.metadata.get("relevance_score", 0.0) for d in dual_docs), default=0.0)
        ck_boost = 1.0 if max_dual_score > 0.8 else 1.4
        for doc in all_candidates:
            if doc.metadata.get("doc_type") == "cooking_knowledge":
                doc.metadata["final_score"] = doc.metadata["final_score"] * ck_boost

        # 6. 去重 + 按 final_score 降序排序
        seen_doc_ids = set()
        merged_docs = []
        for doc in sorted(all_candidates, key=lambda d: d.metadata["final_score"], reverse=True):
            doc_id = doc.metadata.get("node_id", hash(doc.page_content))
            if doc_id not in seen_doc_ids:
                seen_doc_ids.add(doc_id)
                doc.metadata["merge_order"] = len(merged_docs)
                merged_docs.append(doc)

        final_docs = merged_docs[:top_k]

        logger.info(f"三路融合：从共{len(all_candidates)}个候选合并为{len(final_docs)}个文档"
                    f" (dual:{len(dual_docs)} vec:{len(vector_docs)} bm25:{len(bm25_docs)})")
        return final_docs
        
    def close(self):
        """关闭资源连接"""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j连接已关闭") 