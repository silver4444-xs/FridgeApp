"""
基于图数据库的RAG系统配置文件
所有敏感凭证通过环境变量注入，不硬编码默认值。
"""

import os
from typing import Dict, Any

from pydantic import BaseModel


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


class GraphRAGConfig(BaseModel):
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

    def model_post_init(self, __context) -> None:
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
        return self.model_dump()

# 延迟创建默认配置 (需先加载 .env 中的环境变量)
def get_default_config() -> GraphRAGConfig:
    return GraphRAGConfig()

# 向后兼容: 允许直接访问，但会在 __post_init__ 中验证凭证
# 建议使用 get_default_config() 并在调用前确保 dotenv 已加载
DEFAULT_CONFIG = None


# ═══════════════════════════════════════════════════════════════
# P2-C: 中间件集中配置 — 替代散落在各文件中的硬编码值
# ═══════════════════════════════════════════════════════════════

class MiddlewareConfig(BaseModel):
    """中间件可调参数 —— 一处修改全局生效。

    被 create_fridge_middleware() 读取，所有阈值/超时/重试参数集中管理。
    可通过环境变量覆盖（优先级高于默认值）。
    """

    # ── CircuitBreaker (P0) ──
    circuit_breaker_failure_threshold: int = 3
    circuit_breaker_cooldown_seconds: float = 30.0

    # ── ModelCallLimit ──
    main_model_call_limit: int = 15
    subagent_model_call_limit: int = 10

    # ── Summarization (P1-A 轻量模型) ──
    summarization_trigger_tokens: int = 4000
    summarization_keep_messages: int = 10

    # ── ModelRetry ──
    model_retry_max_retries: int = 3
    model_retry_initial_delay: float = 1.0
    model_retry_max_delay: float = 30.0
    model_retry_backoff_factor: float = 2.0

    # ── ToolRetry ──
    tool_retry_max_retries: int = 2
    tool_retry_initial_delay: float = 0.5
    tool_retry_max_delay: float = 10.0

    # ── InputGuard (P1-B) ──
    input_guard_max_length: int = 2000

    # ── HITL (P1-D) ──
    hitl_timeout_seconds: float = 30.0


# 全局单例 — lifespan 启动时可通过环境变量微调
middleware_config = MiddlewareConfig()


# ═══════════════════════════════════════════════════════════════
# Phase 2: 可靠性与弹性集中配置 — 连接池上限 + 超时预算 + httpx 超时
# ═══════════════════════════════════════════════════════════════

class ReliabilityConfig(BaseModel):
    """可靠性与弹性参数 —— 一处修改全局生效。

    被 server.py / neo4j_client.py / chat_relay.py / main.py /
    subagents.py / generation_integration.py 读取。

    总超时预算构成:
      - LLM 流式总预算 60s  (stream_total_timeout_seconds)
      - 单事件超时 30s      (stream_event_timeout_seconds)
      - ModelRetry max_delay 30s (见 MiddlewareConfig.model_retry_max_delay)
    """

    # ── PostgreSQL 连接池 ──
    pg_pool_min_size: int = 1
    pg_pool_max_size: int = 10

    # ── Neo4j 连接池 ──
    neo4j_max_connection_pool_size: int = 50
    neo4j_connection_timeout: float = 10.0
    neo4j_max_connection_lifetime: float = 3600.0

    # ── 流式超时预算 ──
    stream_total_timeout_seconds: float = 60.0
    stream_event_timeout_seconds: float = 30.0

    # ── httpx 超时 (connect/write/pool 共用, read 按上下文分三档) ──
    # 注意: 分档保留各上下文既有语义 (generation 流式需 120s)，仅统一「管理」，不强行统一「数值」。
    http_connect_timeout: float = 10.0
    http_write_timeout: float = 10.0
    http_pool_timeout: float = 10.0
    agent_http_read_timeout: float = 60.0
    subagent_http_read_timeout: float = 30.0
    generation_http_read_timeout: float = 120.0

    def model_post_init(self, __context) -> None:
        """从环境变量覆盖关键可调参数（可选，缺省用默认值）。"""
        self.pg_pool_max_size = int(_env_or("PG_POOL_MAX_SIZE", str(self.pg_pool_max_size)))
        self.neo4j_max_connection_pool_size = int(
            _env_or("NEO4J_POOL_MAX_SIZE", str(self.neo4j_max_connection_pool_size))
        )
        self.stream_total_timeout_seconds = float(
            _env_or("STREAM_TOTAL_TIMEOUT", str(self.stream_total_timeout_seconds))
        )
        self.stream_event_timeout_seconds = float(
            _env_or("STREAM_EVENT_TIMEOUT", str(self.stream_event_timeout_seconds))
        )


# 全局单例 — 可被环境变量 PG_POOL_MAX_SIZE / NEO4J_POOL_MAX_SIZE /
# STREAM_TOTAL_TIMEOUT / STREAM_EVENT_TIMEOUT 覆盖
reliability_config = ReliabilityConfig()