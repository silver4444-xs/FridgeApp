"""
混合检索三路融合去重逻辑的回归测试 (P0 检索召回修复)。

验证: 同一文档在多路命中时, 分数应累加而非取单路 max。

背景: 旧实现按 final_score 降序取首个(即 max)去重, 导致权重最高的向量路(0.5)
      压制 BM25 精确菜名匹配(0.3), 出现「口水鸡怎么做」召回「姜炒鸡」的错误。

本测试用 mock 构造三路结果, 不依赖 Neo4j / Milvus。
"""

from langchain_core.documents import Document

from rag_modules.hybrid_retrieval import HybridRetrievalModule


def _doc(node_id, content, **meta):
    return Document(page_content=content, metadata={"node_id": node_id, **meta})


class _FakeBM25:
    """模拟 BM25Okapi: get_scores 返回固定分数列表。"""

    def __init__(self, scores):
        self._scores = scores

    def get_scores(self, tokens):
        return list(self._scores)


def test_fusion_accumulates_multipath_hits():
    """口水鸡在多路命中应累加反超 姜炒鸡(仅向量单路高分)。"""
    # 图路 (权重 0.2): 口水鸡 0.7, 姜炒鸡 0.5 → min-max 后 1.0 / 0.0
    dual_docs = [
        _doc("口水鸡", "口水鸡做法", relevance_score=0.7),
        _doc("姜炒鸡", "姜炒鸡做法", relevance_score=0.5),
    ]
    # 向量路 (权重 0.5): 姜炒鸡排第一, 口水鸡第二, 其他垫底 → 1.0 / 0.6 / 0.0
    vector_docs = [
        _doc("姜炒鸡", "姜炒鸡做法", score=0.95),
        _doc("口水鸡", "口水鸡做法", score=0.85),
        _doc("其他菜", "其他做法", score=0.70),
    ]
    # BM25 路 (权重 0.3): 精确命中口水鸡 (姜炒鸡不在 top_k)
    bm25_docs = [_doc("口水鸡", "口水鸡做法")]

    module = object.__new__(HybridRetrievalModule)
    module.dual_level_retrieval = lambda q, k: dual_docs
    module.vector_search_enhanced = lambda q, k: vector_docs
    module._bm25 = _FakeBM25([3.0])
    module._bm25_docs = bm25_docs

    results = module.hybrid_search("口水鸡怎么做", top_k=3)

    # 累加后: 口水鸡 0.2+0.3+0.3=0.8 > 姜炒鸡 0.0+0.5=0.5
    assert results[0].metadata["node_id"] == "口水鸡", (
        f"期望口水鸡排第一, 实际 {results[0].metadata['node_id']}"
    )
    # 多路命中应被记录为合并的 search_method
    assert "+" in results[0].metadata["search_method"], (
        f"口水鸡应记录多路命中, 实际 {results[0].metadata['search_method']}"
    )
