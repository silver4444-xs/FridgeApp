"""
ReliabilityConfig 单元测试 — 默认值 + 环境变量覆盖 + Neo4j pool kwargs 透传。

Phase 2 (可靠性与弹性) 验证: 连接池上限 / 超时预算 / httpx 超时集中配置。
确保 config.ReliabilityConfig 是唯一真相源，且环境变量可覆盖关键可调参数。
"""
from unittest.mock import MagicMock, patch

from config import ReliabilityConfig, reliability_config


class TestReliabilityConfigDefaults:
    """默认值断言 — 不依赖环境变量也能得到安全默认。"""

    def test_pg_pool_defaults(self):
        c = ReliabilityConfig()
        assert c.pg_pool_min_size == 1
        assert c.pg_pool_max_size == 10

    def test_neo4j_pool_defaults(self):
        c = ReliabilityConfig()
        assert c.neo4j_max_connection_pool_size == 50
        assert c.neo4j_connection_timeout == 10.0
        assert c.neo4j_max_connection_lifetime == 3600.0

    def test_stream_timeout_budget_defaults(self):
        c = ReliabilityConfig()
        assert c.stream_total_timeout_seconds == 60.0
        assert c.stream_event_timeout_seconds == 30.0

    def test_http_timeout_defaults(self):
        c = ReliabilityConfig()
        # connect/write/pool 共用一档
        assert c.http_connect_timeout == 10.0
        assert c.http_write_timeout == 10.0
        assert c.http_pool_timeout == 10.0
        # read 按上下文分三档，保留各上下文既有语义
        assert c.agent_http_read_timeout == 60.0
        assert c.subagent_http_read_timeout == 30.0
        assert c.generation_http_read_timeout == 120.0


class TestReliabilityConfigEnvOverride:
    """环境变量覆盖 — 运维可不改代码直接调参。"""

    def test_env_overrides(self, monkeypatch):
        monkeypatch.setenv("PG_POOL_MAX_SIZE", "25")
        monkeypatch.setenv("NEO4J_POOL_MAX_SIZE", "80")
        monkeypatch.setenv("STREAM_TOTAL_TIMEOUT", "90")
        monkeypatch.setenv("STREAM_EVENT_TIMEOUT", "15")

        c = ReliabilityConfig()

        assert c.pg_pool_max_size == 25
        assert c.neo4j_max_connection_pool_size == 80
        assert c.stream_total_timeout_seconds == 90.0
        assert c.stream_event_timeout_seconds == 15.0


class TestNeo4jPoolKwargsPassthrough:
    """Neo4j pool kwargs 透传 — 验证配置确实注入到 GraphDatabase.driver。"""

    def test_driver_receives_pool_config(self):
        from rag_modules.neo4j_client import Neo4jClient
        import rag_modules.neo4j_client as nc

        Neo4jClient._driver = None
        with patch.object(nc.GraphDatabase, "driver") as mock_driver:
            mock_driver.return_value = MagicMock()
            Neo4jClient.get_driver(
                "bolt://localhost:7687", "neo4j", "secret", "neo4j"
            )

        kwargs = mock_driver.call_args.kwargs
        assert kwargs["max_connection_pool_size"] == reliability_config.neo4j_max_connection_pool_size
        assert kwargs["connection_timeout"] == reliability_config.neo4j_connection_timeout
        assert kwargs["max_connection_lifetime"] == reliability_config.neo4j_max_connection_lifetime
