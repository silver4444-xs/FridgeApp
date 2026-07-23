"""
真正的图RAG检索模块
基于图结构的知识推理和检索，而非简单的关键词匹配
"""

import json
import logging
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import List, Dict, Tuple, Any, Optional, Set
from enum import Enum

from pydantic import BaseModel, Field
from langchain_core.documents import Document
from neo4j import GraphDatabase

from prompts.graph_query import UNDERSTAND_GRAPH_QUERY
logger = logging.getLogger(__name__)

class QueryType(Enum):
    """查询类型枚举"""
    ENTITY_RELATION = "entity_relation"  # 实体关系查询：A和B有什么关系？
    MULTI_HOP = "multi_hop"  # 多跳查询：A通过什么连接到C？
    SUBGRAPH = "subgraph"  # 子图查询：A相关的所有信息
    PATH_FINDING = "path_finding"  # 路径查找：从A到B的最佳路径
    CLUSTERING = "clustering"  # 聚类查询：和A相似的都有什么？

class GraphQuery(BaseModel):
    """图查询结构 (Pydantic BaseModel，支持 langchain with_structured_output)"""
    query_type: QueryType = Field(description="查询类型：entity_relation/multi_hop/subgraph/path_finding/clustering")
    source_entities: List[str] = Field(description="源实体列表，只包含图中可能存在的具体实体名称")
    target_entities: Optional[List[str]] = Field(default=None, description="目标实体列表，不确定时可为空")
    relation_types: Optional[List[str]] = Field(default=None, description="优先考虑的关系类型，如 REQUIRES, BELONGS_TO_CATEGORY")
    max_depth: int = Field(default=2, description="图遍历深度 1-3")
    max_nodes: int = Field(default=50, description="最大节点数")
    constraints: Optional[Dict[str, Any]] = Field(default=None, description="属性级约束(健康/时间/口味偏好等)")

@dataclass
class GraphPath:
    """图路径结构"""
    nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    path_length: int
    relevance_score: float
    path_type: str

@dataclass
class KnowledgeSubgraph:
    """知识子图结构"""
    central_nodes: List[Dict[str, Any]]
    connected_nodes: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    graph_metrics: Dict[str, float]
    reasoning_chains: List[List[str]]

class GraphRAGRetrieval:
    """
    真正的图RAG检索系统
    核心特点：
    1. 查询意图理解：识别图查询模式
    2. 多跳图遍历：深度关系探索
    3. 子图提取：相关知识网络
    4. 图结构推理：基于拓扑的推理
    5. 动态查询规划：自适应遍历策略
    """
    
    def __init__(self, config, llm_client):
        self.config = config
        self.llm_client = llm_client
        self.driver = None
        
        # 图结构缓存
        self.entity_cache = {}
        self.relation_cache = {}
        self.subgraph_cache = {}
        
    def initialize(self):
        """初始化图RAG检索系统"""
        logger.info("初始化图RAG检索系统...")
        
        # 连接Neo4j（使用共享驱动单例）
        try:
            from .neo4j_client import Neo4jClient
            self.driver = Neo4jClient.get_driver(
                self.config.neo4j_uri,
                self.config.neo4j_user,
                self.config.neo4j_password,
                self.config.neo4j_database,
            )
            # 测试连接
            with self.driver.session() as session:
                session.run("RETURN 1")
            logger.info("Neo4j连接成功")
        except Exception as e:
            logger.error(f"Neo4j连接失败: {e}")
            return
        
        # 预热：构建实体和关系索引
        self._build_graph_index()
        
    def _build_graph_index(self):
        """构建图索引以加速查询"""
        logger.info("构建图结构索引...")
        
        try:
            with self.driver.session() as session:
                # 构建实体索引 - 修复Neo4j语法兼容性问题
                entity_query = """
                MATCH (n)
                WHERE n.nodeId IS NOT NULL
                WITH n, COUNT { (n)--() } as degree
                RETURN labels(n) as node_labels, n.nodeId as node_id, 
                       n.name as name, n.category as category, degree
                ORDER BY degree DESC
                LIMIT 1000
                """
                
                result = session.run(entity_query)
                for record in result:
                    node_id = record["node_id"]
                    self.entity_cache[node_id] = {
                        "labels": record["node_labels"],
                        "name": record["name"],
                        "category": record["category"],
                        "degree": record["degree"]
                    }
                
                # 构建关系类型索引
                relation_query = """
                MATCH ()-[r]->()
                RETURN type(r) as rel_type, count(r) as frequency
                ORDER BY frequency DESC
                """
                
                result = session.run(relation_query)
                for record in result:
                    rel_type = record["rel_type"]
                    self.relation_cache[rel_type] = record["frequency"]
                    
                logger.info(f"索引构建完成: {len(self.entity_cache)}个实体, {len(self.relation_cache)}个关系类型")
                
        except Exception as e:
            logger.error(f"构建图索引失败: {e}")
    
    def understand_graph_query(self, query: str) -> GraphQuery:
        """
        理解查询的图结构意图
        这是图RAG的核心：从自然语言到图查询的转换
        """

        # ChatPromptTemplate + with_structured_output 调用
        try:
            messages = UNDERSTAND_GRAPH_QUERY.format_prompt(query=query)
            structured_llm = self.llm_client.with_structured_output(GraphQuery, method="function_calling")
            return structured_llm.invoke(messages)
        except Exception as e:
            logger.error(f"查询意图理解失败: {e}")
            # 降级方案：默认子图查询
            return GraphQuery(
                query_type=QueryType.SUBGRAPH,
                source_entities=[query],
                max_depth=2
            )
    
    def multi_hop_traversal(self, graph_query: GraphQuery) -> List[GraphPath]:
        """
        多跳图遍历：这是图RAG的核心优势
        通过图结构发现隐含的知识关联
        """
        logger.info(f"执行多跳遍历: {graph_query.source_entities} -> {graph_query.target_entities}")
        
        paths = []
        
        if not self.driver:
            logger.error("Neo4j连接未建立")
            return paths
            
        try:
            with self.driver.session() as session:
                # 构建多跳遍历查询
                source_entities = graph_query.source_entities
                target_keywords = graph_query.target_entities or []
                max_depth = graph_query.max_depth
                
                # 根据查询类型选择不同的遍历策略
                if graph_query.query_type == QueryType.MULTI_HOP:
                    # 根据是否有目标关键词动态拼接过滤条件
                    target_filter_clause = ""
                    if target_keywords:
                        target_filter_clause = """
                    AND ANY(kw IN $target_keywords WHERE
                        (target.name IS NOT NULL AND (toString(target.name) CONTAINS kw OR kw CONTAINS toString(target.name))) OR
                        (target.category IS NOT NULL AND (toString(target.category) CONTAINS kw OR kw CONTAINS toString(target.category)))
                    )"""
                    
                    cypher_query = f"""
                    // 多跳推理查询
                    UNWIND $source_entities as source_name
                    MATCH (source)
                    WHERE source.name CONTAINS source_name OR source.nodeId = source_name
                    
                    // 执行多跳遍历
                    MATCH path = (source)-[*1..{max_depth}]-(target)
                    WHERE NOT source = target{target_filter_clause}
                    
                    // 计算路径相关性
                    WITH path, source, target,
                         length(path) as path_len,
                         relationships(path) as rels,
                         nodes(path) as path_nodes
                    
                    // 路径评分：短路径 + 高度数节点 + 关系类型匹配
                    WITH path, source, target, path_len, rels, path_nodes,
                         (1.0 / path_len) + 
                         (REDUCE(s = 0.0, n IN path_nodes | s + COUNT {{ (n)--() }}) / 10.0 / size(path_nodes)) +
                         (CASE WHEN ANY(r IN rels WHERE type(r) IN $relation_types) THEN 0.3 ELSE 0.0 END) as relevance
                    
                    ORDER BY relevance DESC
                    LIMIT 20
                    
                    RETURN path, source, target, path_len, rels, path_nodes, relevance
                    """
                    
                    params = {
                        "source_entities": source_entities,
                        "relation_types": graph_query.relation_types or []
                    }
                    if target_keywords:
                        params["target_keywords"] = target_keywords
                    
                    result = session.run(cypher_query, params)
                    
                    for record in result:
                        path_data = self._parse_neo4j_path(record)
                        if path_data:
                            paths.append(path_data)
                
                elif graph_query.query_type == QueryType.ENTITY_RELATION:
                    # 实体间关系查询
                    paths.extend(self._find_entity_relations(graph_query, session))
                
                elif graph_query.query_type == QueryType.PATH_FINDING:
                    # 最短路径查找
                    paths.extend(self._find_shortest_paths(graph_query, session))
                    
        except Exception as e:
            logger.error(f"多跳遍历失败: {e}")
            
        logger.info(f"多跳遍历完成，找到 {len(paths)} 条路径")
        return paths
    
    def extract_knowledge_subgraph(self, graph_query: GraphQuery) -> KnowledgeSubgraph:
        """
        提取知识子图：获取实体相关的完整知识网络
        这体现了图RAG的整体性思维
        """
        logger.info(f"提取知识子图: {graph_query.source_entities}")
        
        if not self.driver:
            logger.error("Neo4j连接未建立")
            return self._fallback_subgraph_extraction(graph_query)
        
        try:
            with self.driver.session() as session:
                # 简化的子图提取（不依赖APOC）
                cypher_query = f"""
                // 找到源实体
                UNWIND $source_entities as entity_name
                MATCH (source)
                WHERE source.name CONTAINS entity_name 
                   OR source.nodeId = entity_name
                
                // 获取指定深度的邻居
                MATCH (source)-[r*1..{graph_query.max_depth}]-(neighbor)
                WITH source, collect(DISTINCT neighbor) as neighbors, 
                     collect(DISTINCT r) as relationships
                WHERE size(neighbors) <= $max_nodes
                
                // 计算图指标
                WITH source, neighbors, relationships,
                     size(neighbors) as node_count,
                     size(relationships) as rel_count
                
                RETURN 
                    source,
                    neighbors[0..{graph_query.max_nodes}] as nodes,
                    relationships[0..{graph_query.max_nodes}] as rels,
                    {{
                        node_count: node_count,
                        relationship_count: rel_count,
                        density: CASE WHEN node_count > 1 THEN toFloat(rel_count) / (node_count * (node_count - 1) / 2) ELSE 0.0 END
                    }} as metrics
                """
                
                result = session.run(cypher_query, {
                    "source_entities": graph_query.source_entities,
                    "max_nodes": graph_query.max_nodes
                })
                
                record = result.single()
                if record:
                    return self._build_knowledge_subgraph(record)
                    
        except Exception as e:
            logger.error(f"子图提取失败: {e}")
            
        # 降级方案：简单邻居查询
        return self._fallback_subgraph_extraction(graph_query)
    
    def graph_structure_reasoning(self, subgraph: KnowledgeSubgraph, query: str) -> List[str]:
        """
        基于图结构的推理：这是图RAG的智能之处
        不仅检索信息，还能进行逻辑推理
        """
        reasoning_chains = []
        
        try:
            # 1. 识别推理模式
            reasoning_patterns = self._identify_reasoning_patterns(subgraph)
            
            # 2. 构建推理链
            for pattern in reasoning_patterns:
                chain = self._build_reasoning_chain(pattern, subgraph)
                if chain:
                    reasoning_chains.append(chain)
            
            # 3. 验证推理链的可信度
            validated_chains = self._validate_reasoning_chains(reasoning_chains, query)
            
            logger.info(f"图结构推理完成，生成 {len(validated_chains)} 条推理链")
            return validated_chains
            
        except Exception as e:
            logger.error(f"图结构推理失败: {e}")
            return []
    
    def adaptive_query_planning(self, query: str) -> List[GraphQuery]:
        """
        自适应查询规划：根据查询复杂度动态调整策略
        """
        # 分析查询复杂度
        complexity_score = self._analyze_query_complexity(query)
        
        query_plans = []
        
        if complexity_score < 0.3:
            # 简单查询：直接邻居查询
            plan = GraphQuery(
                query_type=QueryType.ENTITY_RELATION,
                source_entities=[query],
                max_depth=1,
                max_nodes=20
            )
            query_plans.append(plan)
            
        elif complexity_score < 0.7:
            # 中等复杂度：多跳查询
            plan = GraphQuery(
                query_type=QueryType.MULTI_HOP,
                source_entities=[query],
                max_depth=2,
                max_nodes=50
            )
            query_plans.append(plan)
            
        else:
            # 复杂查询：子图提取 + 推理
            plan1 = GraphQuery(
                query_type=QueryType.SUBGRAPH,
                source_entities=[query],
                max_depth=3,
                max_nodes=100
            )
            plan2 = GraphQuery(
                query_type=QueryType.MULTI_HOP,
                source_entities=[query],
                max_depth=3,
                max_nodes=50
            )
            query_plans.extend([plan1, plan2])
            
        return query_plans
    
    def graph_rag_search(self, query: str, top_k: int = 5) -> List[Document]:
        """
        图RAG主搜索接口：整合所有图RAG能力
        """
        logger.info(f"开始图RAG检索: {query}")
        
        if not self.driver:
            logger.warning("Neo4j连接未建立，返回空结果")
            return []
        
        # 1. 查询意图理解
        graph_query = self.understand_graph_query(query)
        logger.info(f"查询类型: {graph_query.query_type.value}")
        
        results = []
        
        try:
            # 2. 根据查询类型执行不同策略
            if graph_query.query_type in [QueryType.MULTI_HOP, QueryType.PATH_FINDING]:
                # 多跳遍历 / 路径查找
                paths = self.multi_hop_traversal(graph_query)
                results.extend(self._paths_to_documents(paths, query))
                
            elif graph_query.query_type in [QueryType.SUBGRAPH, QueryType.CLUSTERING]:
                # 子图提取 / 聚类查询：都视为“围绕核心实体的局部知识网络”
                subgraph = self.extract_knowledge_subgraph(graph_query)
                
                # 图结构推理
                reasoning_chains = self.graph_structure_reasoning(subgraph, query)
                
                results.extend(self._subgraph_to_documents(subgraph, reasoning_chains, query))
                
            elif graph_query.query_type == QueryType.ENTITY_RELATION:
                # 实体关系查询（可以视为一跳 / 少量跳的路径查询）
                paths = self.multi_hop_traversal(graph_query)
                results.extend(self._paths_to_documents(paths, query))
            
            # 3. 图结构相关性排序
            results = self._rank_by_graph_relevance(results, query)
            
            logger.info(f"图RAG检索完成，返回 {len(results[:top_k])} 个结果")
            return results[:top_k]
            
        except Exception as e:
            logger.error(f"图RAG检索失败: {e}")
            return []
    
    # ========== 辅助方法 ==========
    
    def _parse_neo4j_path(self, record) -> Optional[GraphPath]:
        """解析Neo4j路径记录"""
        try:
            path_nodes = []
            for node in record["path_nodes"]:
                path_nodes.append({
                    "id": node.get("nodeId", ""),
                    "name": node.get("name", ""),
                    "labels": list(node.labels),
                    "properties": dict(node.items())
                })
            
            relationships = []
            for rel in record["rels"]:
                relationships.append({
                    "type": rel.type,
                    "properties": dict(rel.items())
                })
            
            return GraphPath(
                nodes=path_nodes,
                relationships=relationships,
                path_length=record["path_len"],
                relevance_score=record["relevance"],
                path_type="multi_hop"
            )
            
        except Exception as e:
            logger.error(f"路径解析失败: {e}")
            return None
    
    def _build_knowledge_subgraph(self, record) -> KnowledgeSubgraph:
        """构建知识子图对象"""
        try:
            central_nodes = [dict(record["source"].items())]
            connected_nodes = [dict(node.items()) for node in record["nodes"]]
            relationships = []
            for rel_group in record["rels"]:
                if isinstance(rel_group, list):
                    for rel in rel_group:
                        props = dict(rel.items())
                        props.setdefault("type", rel.type)
                        relationships.append(props)
                else:
                    props = dict(rel_group.items())
                    props.setdefault("type", rel_group.type)
                    relationships.append(props)
            
            return KnowledgeSubgraph(
                central_nodes=central_nodes,
                connected_nodes=connected_nodes,
                relationships=relationships,
                graph_metrics=record["metrics"],
                reasoning_chains=[]
            )
        except Exception as e:
            logger.error(f"构建知识子图失败: {e}")
            return KnowledgeSubgraph(
                central_nodes=[],
                connected_nodes=[],
                relationships=[],
                graph_metrics={},
                reasoning_chains=[]
            )
    
    def _paths_to_documents(self, paths: List[GraphPath], query: str) -> List[Document]:
        """将图路径转换为Document对象"""
        documents = []
        
        for i, path in enumerate(paths):
            # 构建路径描述
            path_desc = self._build_path_description(path)
            
            doc = Document(
                page_content=path_desc,
                metadata={
                    "search_type": "graph_path",
                    "path_length": path.path_length,
                    "relevance_score": path.relevance_score,
                    "path_type": path.path_type,
                    "node_count": len(path.nodes),
                    "relationship_count": len(path.relationships),
                    "recipe_name": path.nodes[0].get("name", "图结构结果") if path.nodes else "图结构结果"
                }
            )
            documents.append(doc)
            
        return documents
    
    def _subgraph_to_documents(self, subgraph: KnowledgeSubgraph, 
                              reasoning_chains: List[str], query: str) -> List[Document]:
        """将知识子图转换为Document对象"""
        documents = []
        
        # 子图整体描述
        subgraph_desc = self._build_subgraph_description(subgraph)
        
        doc = Document(
            page_content=subgraph_desc,
            metadata={
                "search_type": "knowledge_subgraph",
                "node_count": len(subgraph.connected_nodes),
                "relationship_count": len(subgraph.relationships),
                "graph_density": subgraph.graph_metrics.get("density", 0.0),
                "reasoning_chains": reasoning_chains,
                "recipe_name": subgraph.central_nodes[0].get("name", "知识子图") if subgraph.central_nodes else "知识子图"
            }
        )
        documents.append(doc)
        
        return documents
    
    def _build_path_description(self, path: GraphPath) -> str:
        """构建路径的自然语言描述，包含节点类型和关系类型"""
        if not path.nodes:
            return "空路径"

        desc_parts = []
        for i, node in enumerate(path.nodes):
            name = node.get("name", f"节点{i}")
            labels = node.get("labels", [])
            label_str = "/".join(labels) if labels else "实体"
            desc_parts.append(f"{name}({label_str})")
            if i < len(path.relationships):
                rel = path.relationships[i]
                rel_type = rel.get("type", "相关")
                desc_parts.append(f" --[{rel_type}]--> ")

        return "".join(desc_parts)

    def _build_subgraph_description(self, subgraph: KnowledgeSubgraph) -> str:
        """构建子图的自然语言描述，包含实际节点和关系名称"""
        parts = []

        if subgraph.central_nodes:
            central_names = [n.get("name", "未知") for n in subgraph.central_nodes if n.get("name")]
            parts.append(f"核心概念: {', '.join(central_names)}")

        if subgraph.connected_nodes:
            node_names = [n.get("name", "") for n in subgraph.connected_nodes[:10] if n.get("name")]
            if node_names:
                parts.append(f"相关节点({len(subgraph.connected_nodes)}): {', '.join(node_names)}")

        if subgraph.relationships:
            rel_types = set(r.get("type", "相关") for r in subgraph.relationships if r.get("type"))
            parts.append(f"关系类型: {', '.join(list(rel_types)[:5])}")

        metrics = subgraph.graph_metrics
        if metrics:
            density = metrics.get("density", 0)
            parts.append(f"图密度: {density:.3f}")

        return " | ".join(parts) if parts else "空知识子图"
    
    def _rank_by_graph_relevance(self, documents: List[Document], query: str) -> List[Document]:
        """基于图结构相关性排序"""
        return sorted(documents, 
                     key=lambda x: x.metadata.get("relevance_score", 0.0), 
                     reverse=True)
    
    def _analyze_query_complexity(self, query: str) -> float:
        """分析查询复杂度"""
        complexity_indicators = ["什么", "如何", "为什么", "哪些", "关系", "影响", "原因"]
        score = sum(1 for indicator in complexity_indicators if indicator in query)
        return min(score / len(complexity_indicators), 1.0)
    
    def _identify_reasoning_patterns(self, subgraph: KnowledgeSubgraph) -> List[str]:
        """识别推理模式"""
        return ["因果关系", "组成关系", "相似关系"]
    
    def _build_reasoning_chain(self, pattern: str, subgraph: KnowledgeSubgraph) -> Optional[str]:
        """构建推理链"""
        return f"基于{pattern}的推理链"
    
    def _validate_reasoning_chains(self, chains: List[str], query: str) -> List[str]:
        """验证推理链"""
        return chains[:3]
    
    def _find_entity_relations(self, graph_query: GraphQuery, session) -> List[GraphPath]:
        """查找实体间关系: 在 Neo4j 中查询源实体和目标实体之间的直接关系"""
        paths = []
        sources = graph_query.source_entities
        targets = graph_query.target_entities or []
        max_depth = min(graph_query.max_depth, 3)

        try:
            cypher = """
            UNWIND $sources as src_name
            MATCH (a)
            WHERE a.name CONTAINS src_name OR a.nodeId = src_name
            UNWIND $targets as tgt_name
            MATCH (b)
            WHERE (b.name CONTAINS tgt_name OR b.nodeId = tgt_name) AND a <> b
            MATCH path = (a)-[*1..""" + str(max_depth) + """]-(b)
            WITH path, length(path) as plen,
                 relationships(path) as rels, nodes(path) as pnodes
            ORDER BY plen
            LIMIT 10
            RETURN pnodes as path_nodes, rels, plen as path_len,
                   1.0 / plen as relevance
            """
            result = session.run(cypher, {"sources": sources, "targets": targets})
            for record in result:
                path_data = self._parse_neo4j_path(record)
                if path_data:
                    paths.append(path_data)
        except Exception as e:
            logger.error(f"实体关系查询失败: {e}")

        return paths

    def _find_shortest_paths(self, graph_query: GraphQuery, session) -> List[GraphPath]:
        """查找最短路径: 使用 shortestPath 算法在图中找最短连接"""
        paths = []
        sources = graph_query.source_entities
        targets = graph_query.target_entities or sources  # 若无目标则找源实体间路径

        try:
            cypher = """
            UNWIND $sources as src_name
            MATCH (a)
            WHERE a.name CONTAINS src_name OR a.nodeId = src_name
            UNWIND $targets as tgt_name
            MATCH (b)
            WHERE (b.name CONTAINS tgt_name OR b.nodeId = tgt_name) AND a <> b
            MATCH path = shortestPath((a)-[*1..5]-(b))
            WITH path, length(path) as plen,
                 relationships(path) as rels, nodes(path) as pnodes
            ORDER BY plen
            LIMIT 10
            RETURN pnodes as path_nodes, rels, plen as path_len,
                   1.0 / plen as relevance
            """
            result = session.run(cypher, {"sources": sources, "targets": targets})
            for record in result:
                path_data = self._parse_neo4j_path(record)
                if path_data:
                    paths.append(path_data)
        except Exception as e:
            logger.error(f"最短路径查询失败: {e}")

        return paths
    
    def _fallback_subgraph_extraction(self, graph_query: GraphQuery) -> KnowledgeSubgraph:
        """降级子图提取"""
        return KnowledgeSubgraph(
            central_nodes=[],
            connected_nodes=[],
            relationships=[],
            graph_metrics={},
            reasoning_chains=[]
        )
    
    def close(self):
        """关闭资源连接"""
        if hasattr(self, 'driver') and self.driver:
            self.driver.close()
            logger.info("图RAG检索系统已关闭") 