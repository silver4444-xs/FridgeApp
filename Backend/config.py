"""
基于图数据库的RAG系统配置文件
所有敏感凭证通过环境变量注入，不硬编码默认值。
"""

import os
from dataclasses import dataclass
from typing import Dict, Any


def _require_env(key: str) -> str:
    """读取必需的环境变量，未设置时抛出明确错误。"""
    value = os.getenv(key)
    if not value:
        raise ValueError(
            f"必需的环境变量 {key} 未设置。"
            f"请复制 .env.example 为 .env 并填入真实的凭证值。"
        )
    return value


def _env_or(key: str, default: str) -> str:
    """读取可选的环境变量，未设置时返回默认值。"""
    return os.getenv(key) or default


@dataclass
class GraphRAGConfig:
    """基于图数据库的RAG系统配置类"""

    # Neo4j数据库配置 — 密码从环境变量读取
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    # Milvus配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection_name: str = "cooking_knowledge"
    milvus_dimension: int = 512  # BGE-small-zh-v1.5的向量维度

    # 模型配置
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    llm_model: str = "deepseek-v4-pro"

    # 检索配置（LightRAG Round-robin策略）
    top_k: int = 10

    # 生成配置
    temperature: float = 0.1
    max_tokens: int = 2048

    # 图数据处理配置
    chunk_size: int = 500
    chunk_overlap: int = 50
    max_graph_depth: int = 2  # 图遍历最大深度

    def __post_init__(self):
        """初始化后从环境变量加载敏感凭证，缺失时快速失败。"""
        if not self.neo4j_password:
            self.neo4j_password = _require_env("NEO4J_PASSWORD")
        self.neo4j_uri = _env_or("NEO4J_URI", self.neo4j_uri)
        self.neo4j_user = _env_or("NEO4J_USER", self.neo4j_user)
        self.llm_model = _env_or("LLM_MODEL", "deepseek-v4-pro")
        self.embedding_model = _env_or("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'GraphRAGConfig':
        """从字典创建配置对象"""
        return cls(**config_dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'neo4j_uri': self.neo4j_uri,
            'neo4j_user': self.neo4j_user,
            'neo4j_password': self.neo4j_password,
            'neo4j_database': self.neo4j_database,
            'milvus_host': self.milvus_host,
            'milvus_port': self.milvus_port,
            'milvus_collection_name': self.milvus_collection_name,
            'milvus_dimension': self.milvus_dimension,
            'embedding_model': self.embedding_model,
            'llm_model': self.llm_model,
            'top_k': self.top_k,

            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'chunk_size': self.chunk_size,
            'chunk_overlap': self.chunk_overlap,
            'max_graph_depth': self.max_graph_depth
        }

# 延迟创建默认配置 (需先加载 .env 中的环境变量)
def get_default_config() -> GraphRAGConfig:
    return GraphRAGConfig()

# 向后兼容: 允许直接访问，但会在 __post_init__ 中验证凭证
# 建议使用 get_default_config() 并在调用前确保 dotenv 已加载
DEFAULT_CONFIG = None