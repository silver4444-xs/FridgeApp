"""
共享 Neo4j 驱动单例 — 全局唯一连接池。

替代各模块独立创建 GraphDatabase.driver 的做法（P1-4 修复）。
graph_data_preparation、hybrid_retrieval、graph_rag_retrieval 统一使用此客户端。
"""
import logging
from neo4j import GraphDatabase

logger = logging.getLogger(__name__)


class Neo4jClient:
    """全应用共享的 Neo4j 驱动单例。

    用法:
        driver = Neo4jClient.get_driver(uri, user, password)
        with driver.session() as session:
            session.run("MATCH (n) RETURN count(n)")
        # 应用退出时:
        Neo4jClient.close()
    """

    _driver = None

    @classmethod
    def get_driver(cls, uri: str, user: str, password: str, database: str = "neo4j"):
        """获取共享 Neo4j 驱动实例（懒初始化）。"""
        if cls._driver is None:
            cls._driver = GraphDatabase.driver(
                uri, auth=(user, password), database=database,
            )
            try:
                with cls._driver.session() as session:
                    session.run("RETURN 1")
                logger.info(f"Neo4j 共享驱动创建成功: {uri}")
            except Exception as e:
                cls._driver = None
                logger.error(f"Neo4j 连接失败: {e}")
                raise
        return cls._driver

    @classmethod
    def close(cls):
        """关闭驱动连接池。"""
        if cls._driver:
            cls._driver.close()
            cls._driver = None
            logger.info("Neo4j 共享驱动已关闭")
