"""
降级矩阵故障注入测试 (Phase 2 可靠性与弹性)。

mock 注入, 无真实 Neo4j/Milvus/DeepSeek/Jina 依赖:
  - Milvus 挂   → vector_search_enhanced 返回 [] (不抛), hybrid 融合仍出结果
  - Neo4j 挂    → graph_rag_search 返回 [] → route_query 回退 hybrid
  - Jina 挂     → rerank_with_jina 返回粗排候选 (不抛)
  - DeepSeek 挂 → generate_adaptive_answer 返回友好错误字符串 (不抛)
"""
import requests
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document


# ── Milvus 挂 ──────────────────────────────────────────────────

def test_milvus_down_vector_search_degrades_to_empty():
    from rag_modules.hybrid_retrieval import HybridRetrievalModule

    module = HybridRetrievalModule(
        config=MagicMock(),
        milvus_module=MagicMock(),
        data_module=MagicMock(),
        llm_client=MagicMock(),
    )
    module.milvus_module.similarity_search = MagicMock(
        side_effect=Exception("Milvus connection refused")
    )

    docs = module.vector_search_enhanced("红烧肉", top_k=10)

    assert docs == []  # 降级为空, 不抛异常


# ── Neo4j / 图 RAG 挂 ──────────────────────────────────────────

def test_graph_rag_empty_falls_back_to_hybrid():
    from rag_modules.intelligent_query_router import (
        IntelligentQueryRouter, SearchStrategy, QueryAnalysis,
    )

    router = IntelligentQueryRouter(
        traditional_retrieval=MagicMock(),
        graph_rag_retrieval=MagicMock(),
        llm_client=MagicMock(),
        config=MagicMock(),
    )

    # 强制 GRAPH_RAG 策略 + 图可回答 (跳过早期 downgrade 分支)
    router.analyze_query = MagicMock(return_value=QueryAnalysis(
        query_complexity=0.6,
        relationship_intensity=0.6,
        reasoning_required=True,
        entity_count=1,
        recommended_strategy=SearchStrategy.GRAPH_RAG,
        confidence=0.8,
        reasoning="test",
    ))
    router._graph_can_answer = MagicMock(return_value=True)

    # 图 RAG 检索返回空 (Neo4j 挂 → 空子图)
    router.graph_rag_retrieval.graph_rag_search = MagicMock(return_value=[])

    fallback_docs = [
        Document(page_content="红烧肉做法", metadata={"node_id": "1", "recipe_name": "红烧肉"}),
    ]
    router.traditional_retrieval.hybrid_search_with_rerank = MagicMock(
        return_value=fallback_docs,
    )

    docs, analysis, rewritten = router.route_query(
        "红烧肉的做法", top_k=5, enable_rewrite=False, enable_rerank=False,
    )

    assert docs == fallback_docs
    router.traditional_retrieval.hybrid_search_with_rerank.assert_called_once()


# ── Jina 挂 ────────────────────────────────────────────────────

def test_jina_down_returns_coarse_candidates(monkeypatch):
    from rag_modules.reranker import rerank_with_jina

    monkeypatch.setenv("JINA_API_KEY", "test-key")  # 触发真实 API 调用路径
    candidates = [
        Document(page_content=f"doc{i}", metadata={"node_id": str(i)})
        for i in range(5)
    ]

    with patch(
        "rag_modules.reranker.requests.post",
        side_effect=requests.exceptions.ConnectionError("jina down"),
    ):
        result = rerank_with_jina("红烧肉", candidates, top_k=3)

    assert len(result) == 3
    assert result[0].page_content == "doc0"  # 降级为粗排 top_k 截断


# ── DeepSeek 挂 ────────────────────────────────────────────────

def test_deepseek_down_returns_friendly_error(monkeypatch):
    from rag_modules.generation_integration import GenerationIntegrationModule

    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")

    with patch("rag_modules.generation_integration.init_chat_model") as mock_init:
        mock_client = MagicMock()
        mock_client.invoke.side_effect = Exception("DeepSeek API down")
        mock_init.return_value = mock_client

        module = GenerationIntegrationModule()
        result = module.generate_adaptive_answer(
            "红烧肉怎么做",
            [Document(page_content="红烧肉做法...", metadata={"node_id": "1"})],
        )

    assert result.startswith("抱歉")
