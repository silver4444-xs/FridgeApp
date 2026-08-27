"""
P1 图RAG路径描述 + 路由偏斜 的回归测试。

验证:
1. _build_path_description 把 raw 图三元组 `A(Recipe) --[REQUIRES]--> B(Ingredient)`
   翻译为中文可读链 `A（菜品） —需要→ B（食材）`。
2. _enforce_strategy_consistency 在 LLM 自报需要推理/高复杂度却仍推荐
   hybrid_traditional 时, 确定性升级到 graph_rag / combined。

不依赖 Neo4j / Milvus。
"""

from langchain_core.documents import Document

from rag_modules.graph_rag_retrieval import GraphRAGRetrieval, GraphPath
from rag_modules.intelligent_query_router import (
    IntelligentQueryRouter,
    QueryAnalysis,
    SearchStrategy,
)


# ---------- 图RAG 路径描述 ----------

def _path(nodes, relationships):
    return GraphPath(
        nodes=nodes,
        relationships=relationships,
        path_length=len(nodes),
        relevance_score=0.9,
        path_type="ingredient",
    )


def test_path_description_readable_chinese():
    """英文关系类型/节点标签 → 中文可读链, raw 英文消失。"""
    module = object.__new__(GraphRAGRetrieval)
    path = _path(
        nodes=[
            {"name": "口水鸡", "labels": ["Recipe"]},
            {"name": "鸡", "labels": ["Ingredient"]},
            {"name": "母鸡", "labels": ["Ingredient"]},
        ],
        relationships=[
            {"type": "REQUIRES"},
            {"type": "SAME_AS"},
        ],
    )

    result = module._build_path_description(path)

    assert "口水鸡（菜品）" in result
    assert "鸡（食材）" in result
    assert "母鸡（食材）" in result
    assert "—需要→" in result
    assert "—同义于→" in result
    # raw 英文不应残留
    assert "REQUIRES" not in result
    assert "SAME_AS" not in result
    assert "Recipe" not in result
    assert "Ingredient" not in result


def test_path_description_empty():
    module = object.__new__(GraphRAGRetrieval)
    assert module._build_path_description(_path([], [])) == "空路径"


# ---------- 路由偏斜一致性修正 ----------

def _analysis(complexity, relation, reasoning_required, strategy):
    return QueryAnalysis(
        query_complexity=complexity,
        relationship_intensity=relation,
        reasoning_required=reasoning_required,
        entity_count=1,
        recommended_strategy=strategy,
        confidence=0.8,
        reasoning="测试",
    )


def _router():
    return object.__new__(IntelligentQueryRouter)


def test_consistency_upgrades_when_reasoning_required():
    """自报需要推理却推荐 hybrid → 升级 graph_rag。"""
    original = _analysis(0.3, 0.2, True, SearchStrategy.HYBRID_TRADITIONAL)
    result = _router()._enforce_strategy_consistency(original)

    assert result.recommended_strategy == SearchStrategy.GRAPH_RAG
    # 不原地修改 (immutability)
    assert original.recommended_strategy == SearchStrategy.HYBRID_TRADITIONAL


def test_consistency_upgrades_when_high_complexity():
    """高复杂度但未标推理 → 升级 graph_rag。"""
    result = _router()._enforce_strategy_consistency(
        _analysis(0.7, 0.1, False, SearchStrategy.HYBRID_TRADITIONAL)
    )
    assert result.recommended_strategy == SearchStrategy.GRAPH_RAG


def test_consistency_combined_when_both_high():
    """复杂度与关系密度双高 → combined。"""
    result = _router()._enforce_strategy_consistency(
        _analysis(0.7, 0.8, False, SearchStrategy.HYBRID_TRADITIONAL)
    )
    assert result.recommended_strategy == SearchStrategy.COMBINED


def test_consistency_keeps_low_complexity():
    """简单查找保持 hybrid_traditional。"""
    result = _router()._enforce_strategy_consistency(
        _analysis(0.2, 0.1, False, SearchStrategy.HYBRID_TRADITIONAL)
    )
    assert result.recommended_strategy == SearchStrategy.HYBRID_TRADITIONAL


def test_consistency_keeps_explicit_graph():
    """已是 graph_rag 时不降级。"""
    result = _router()._enforce_strategy_consistency(
        _analysis(0.5, 0.5, True, SearchStrategy.GRAPH_RAG)
    )
    assert result.recommended_strategy == SearchStrategy.GRAPH_RAG


# ---------- P0 graph_rag 路由兜底 ----------

class _StubGraphRetrieval:
    def __init__(self, entity_cache=None):
        self.entity_cache = entity_cache or {}


def _router_with_graph(entity_cache):
    router = object.__new__(IntelligentQueryRouter)
    router.graph_rag_retrieval = _StubGraphRetrieval(entity_cache)
    return router


def test_substantive_results_empty_list():
    assert _router()._has_substantive_results([]) is False


def test_substantive_results_placeholders_only():
    docs = [Document(page_content="空知识子图"), Document(page_content="空路径")]
    assert _router()._has_substantive_results(docs) is False


def test_substantive_results_has_real_content():
    docs = [Document(page_content="空知识子图"), Document(page_content="口水鸡的做法")]
    assert _router()._has_substantive_results(docs) is True


def test_graph_can_answer_empty_cache():
    assert _router_with_graph({})._graph_can_answer(["口水鸡"]) is False


def test_graph_can_answer_entity_in_name():
    cache = {"n1": {"name": "猪肉（五花肉）", "labels": ["Ingredient"], "degree": 5}}
    assert _router_with_graph(cache)._graph_can_answer(["猪肉"]) is True


def test_graph_can_answer_entity_matches_nodeid():
    cache = {"recipe_001": {"name": "手撕包菜", "labels": ["Recipe"], "degree": 1}}
    assert _router_with_graph(cache)._graph_can_answer(["recipe_001"]) is True


def test_graph_can_answer_entity_missing():
    cache = {"n1": {"name": "猪肉", "labels": ["Ingredient"], "degree": 5}}
    assert _router_with_graph(cache)._graph_can_answer(["生抽"]) is False


def test_graph_can_answer_empty_entities():
    cache = {"n1": {"name": "猪肉", "labels": ["Ingredient"], "degree": 5}}
    assert _router_with_graph(cache)._graph_can_answer([]) is False
