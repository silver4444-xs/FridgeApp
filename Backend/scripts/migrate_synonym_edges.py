"""
SAME_AS 同义边迁移脚本 (P1-4)

基于 INGREDIENT_SYNONYMS 字典，在 Neo4j 中创建 Ingredient 节点间的 SAME_AS 别名关系。
执行后图遍历可通过 :SAME_AS*0.. 跨同义词跳转。

用法: python -m scripts.migrate_synonym_edges
"""
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate(uri: str, user: str, password: str, database: str = "neo4j"):
    """在 Neo4j 中创建 SAME_AS 同义关系边。"""
    from matching.fuzzy_matcher import INGREDIENT_SYNONYMS
    from rag_modules.neo4j_client import Neo4jClient

    driver = Neo4jClient.get_driver(uri, user, password, database)
    created = 0

    with driver.session() as session:
        session.run(
            "CREATE INDEX ingredient_name IF NOT EXISTS FOR (n:Ingredient) ON (n.name)"
        )
        for name, synonyms in INGREDIENT_SYNONYMS.items():
            for syn in synonyms:
                try:
                    result = session.run("""
                        MATCH (a:Ingredient {name: $name1})
                        MATCH (b:Ingredient {name: $name2})
                        WHERE NOT (a)-[:SAME_AS]->(b)
                        MERGE (a)-[:SAME_AS {source: 'synonym_dict'}]->(b)
                        RETURN a.name, b.name
                    """, name1=name, name2=syn)
                    if list(result):
                        created += 1
                except Exception as e:
                    logger.warning(f"跳过 {name} → {syn}: {e}")

    logger.info(f"SAME_AS 边迁移完成: 创建 {created} 条")
    return created


if __name__ == "__main__":
    import os
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    pwd = os.getenv("NEO4J_PASSWORD", "all-in-rag")
    migrate(uri, user, pwd)
