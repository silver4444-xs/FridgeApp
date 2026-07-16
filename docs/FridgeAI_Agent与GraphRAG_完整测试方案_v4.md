# FridgeAI Agent 与 GraphRAG 完整测试方案 v4

> **核心理念**: 能用框架的 → 全部用框架 | 框架覆盖不到的 → pytest 补充 | 所有代码可直接运行
>
> **最后更新**: 2026-07-09 | **目标**: Phase 1-8 完整覆盖 | **框架数**: 7

---

## 目录

1. [测试战略与金字塔](#一测试战略与金字塔)
2. [框架选型与对比](#二框架选型与对比)
3. [环境准备与安装](#三环境准备与安装)
4. [Layer 1: 单元测试 — pytest](#四layer-1-单元测试--pytest)
5. [Layer 2: RAG 检索与生成 — Ragas](#五layer-2-rag-检索与生成--ragas)
6. [Layer 3: Agent 行为测试 — DeepEval](#六layer-3-agent-行为测试--deepeval)
7. [Layer 4: 集成测试 — pytest + TruLens](#七layer-4-集成测试--pytest--trulens)
8. [Layer 5: 端到端测试 — pytest-asyncio](#八layer-5-端到端测试--pytest-asyncio)
9. [Layer 6: 提示词测试 — Promptfoo](#九layer-6-提示词测试--promptfoo)
10. [Layer 7: 可观测性 — LangSmith](#十layer-7-可观测性--langsmith)
11. [测试数据准备](#十一测试数据准备)
12. [CI/CD 集成 — GitHub Actions](#十二cicd-集成--github-actions)
13. [测试报告模板](#十三测试报告模板)
14. [验收检查清单](#十四验收检查清单)

---

## 一、测试战略与金字塔

### 1.1 分层模型

```
                     ┌─────────────────┐
                     │   E2E / Prompt   │  ← 全链路 + 提示词质量
                     │  (TruLens+PFoo)  │     2-5 分钟/次, PR 合并前
                     ├─────────────────┤
                     │  Agent 行为测试  │  ← 工具选择 + 任务完成
                     │   (DeepEval)     │     30-60 秒/次, 每次 commit
                     ├─────────────────┤
                     │  RAG 检索测试    │  ← 检索精度 + 生成忠实度
                     │   (Ragas)        │     10-30 秒/次, 每次 commit
                     ├─────────────────┤
                     │  单元测试        │  ← 纯逻辑, 无外部依赖
                     │   (pytest)       │     < 5 秒/次, 每次保存
                     └─────────────────┘
```

### 1.2 测试覆盖矩阵

| FridgeAI 功能 | pytest | Ragas | DeepEval | TruLens | Promptfoo | LangSmith |
|:--|:--:|:--:|:--:|:--:|:--:|:--:|
| FuzzyMatcher 归一化/同义词 | x | | | | | |
| InvertedIndex 构建/查找 | x | | | | | |
| RecipeDatabase CRUD | x | | | | | |
| Tool 函数 8个逻辑验证 | x | | | | | |
| FridgeContext → ToolRuntime | x | | | | | |
| Middleware 5层链完整性 | x | | | | | |
| HITL 中断/恢复 | x | | | | | |
| Store 持久化 | x | | | | | |
| Milvus 向量检索精度 | | x | | | | |
| Neo4j 图检索精度 | | x | | | | |
| HybridRetrieval 融合 | | x | | | | |
| Generation Faithfulness | | x | x | x | | |
| Generation AnswerRelevancy | | x | x | x | | |
| Agent 工具选择正确性 | | | x | | x | |
| Agent 任务完成率 | | | x | | | |
| Subagent 路由正确性 | | | x | | | |
| 流式输出事件序列 | x | | | | | |
| WebSocket 协议 | x | | | | | |
| REST 回退端点 | x | | | | | |
| 端到端对话 | | | | x | | |
| System Prompt 约束 | | | | | x | |
| 全链路追踪 | | | | | | x |

---

## 二、框架选型与对比

| 框架 | 定位 | 选型理由 |
|------|------|----------|
| **pytest** + asyncio | 单元/集成 | Python 生态标准, fixture/mock 成熟 |
| **Ragas** | RAG 评测 | RAG 评测事实标准, ContextPrecision/Recall/Faithfulness 全套指标 |
| **DeepEval** | Agent 评测 | 专为 Agent 设计, ToolCorrectnessMetric 直接验证 tool-calling |
| **TruLens** | 联合反馈 | LLM-as-Judge 持续打分, 反馈函数链式评估 |
| **Promptfoo** | 提示词对比 | YAML 声明式, 零代码 prompt 对比+断言, CI 友好 |
| **LangSmith** | 可观测性 | LangChain 官方, Agent 全链路自动追踪 |
| **unittest.mock** | Mock | 标准库, 无额外依赖 |

### 不选用及原因

| 框架 | 原因 |
|------|------|
| LangFuse | 与 LangSmith 功能重叠 |
| MLflow Evaluate | 侧重传统 ML, Agent/RAG 支持弱 |
| Phoenix (Arize) | 需额外部署服务, 不适合轻量测试 |

---

## 三、环境准备与安装

### 3.1 一键安装

```bash
conda activate cook-rag-1

# 核心测试
pip install pytest pytest-asyncio pytest-cov pytest-mock pytest-xdist

# RAG 评测
pip install ragas datasets pandas

# Agent 评测
pip install deepeval

# 联合反馈
pip install trulens trulens-providers-langchain

# 提示词评测 (Node.js)
npm install -g promptfoo

# 可观测性
pip install langsmith

# 工具
pip install httpx faker
```

### 3.2 环境变量 (`Backend/.env.test`, gitignore)

```bash
DEEPSEEK_API_KEY=sk-your-key
EVAL_MODEL=deepseek-v4-flash
EVAL_API_KEY=sk-your-key
EVAL_API_BASE=https://api.deepseek.com/v1
LANGCHAIN_TRACING_V2=false
```

### 3.3 目录结构

```
Backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # 全局 fixtures
│   ├── pytest.ini
│   │
│   ├── unit/                          # Layer 1: 单元测试
│   │   ├── test_fuzzy_matcher.py
│   │   ├── test_inverted_index.py
│   │   ├── test_recipe_database.py
│   │   ├── test_tools.py
│   │   ├── test_models.py
│   │   └── test_context_propagation.py
│   │
│   ├── rag/                           # Layer 2: RAG
│   │   ├── test_retrieval_ragas.py
│   │   ├── test_generation_ragas.py
│   │   └── eval_data/
│   │       └── rag_eval_dataset.json
│   │
│   ├── agent/                         # Layer 3: Agent
│   │   ├── test_tool_selection_deepeval.py
│   │   └── test_task_completion_deepeval.py
│   │
│   ├── integration/                   # Layer 4: 集成
│   │   ├── test_agent_invoke.py
│   │   ├── test_graph_multiturn.py
│   │   └── test_trulens_feedback.py
│   │
│   ├── e2e/                           # Layer 5: E2E
│   │   ├── test_full_conversation.py
│   │   └── test_ws_chat.py
│   │
│   └── prompts/                       # Layer 6: 提示词
│       ├── promptfooconfig.yaml
│       ├── current_system_prompt.txt
│       └── variant_concise.txt
```

---

## 四、Layer 1: 单元测试 — pytest

> 不调 LLM、不连数据库、不连外部服务。纯逻辑，< 5 秒跑完。

### 4.1 pytest.ini

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -v --tb=short --strict-markers -p no:warnings
markers =
    unit: No external dependencies
    rag: Requires Ragas + eval LLM
    agent: Requires DeepEval + eval LLM
    integration: Requires running services
    e2e: Requires full stack
    slow: Slow tests (> 1 second)
timeout = 60
```

### 4.2 conftest.py (全局 Fixtures)

```python
import sys, os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_inventory():
    return [
        {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"},
        {"name": "西红柿", "qty": 3, "cal": 18, "cat": "蔬菜"},
        {"name": "鸡胸肉", "qty": 2, "cal": 133, "cat": "肉蛋生鲜类"},
        {"name": "牛奶", "qty": 1, "cal": 65, "cat": "饮料乳品类"},
    ]


@pytest.fixture
def sample_preferences():
    return {"忌口": ["花生", "海鲜"], "偏好菜系": "川菜", "人数": 2}


@pytest.fixture
def sample_recipes():
    return [
        {
            "id": "r001", "name": "番茄炒蛋", "category": "家常菜",
            "difficulty": "简单", "time": "15分钟",
            "ingredients": [
                {"name": "鸡蛋", "required": True},
                {"name": "番茄", "required": True},
                {"name": "葱", "required": False},
            ],
            "steps": ["打蛋", "炒蛋", "炒番茄", "混合"],
            "tips": "火候要快", "tags": ["快手菜", "下饭"],
        },
        {
            "id": "r002", "name": "宫保鸡丁", "category": "川菜",
            "difficulty": "中等", "time": "30分钟",
            "ingredients": [
                {"name": "鸡胸肉", "required": True},
                {"name": "花生", "required": True},
                {"name": "干辣椒", "required": True},
            ],
            "steps": ["切丁", "腌制", "炒制"],
            "tips": "花生最后放保持脆度", "tags": ["川菜", "下饭"],
        },
        {
            "id": "r003", "name": "牛奶炖蛋", "category": "甜品",
            "difficulty": "简单", "time": "20分钟",
            "ingredients": [
                {"name": "鸡蛋", "required": True},
                {"name": "牛奶", "required": True},
                {"name": "糖", "required": False},
            ],
            "steps": ["打蛋", "加牛奶", "蒸"],
            "tips": "小火慢蒸", "tags": ["甜品", "快手"],
        },
    ]


@pytest.fixture
def mock_recipe_db(sample_recipes):
    from matching.recipe_database import RecipeDatabase
    db = RecipeDatabase()
    db._recipes.clear()
    for r in sample_recipes:
        db._recipes[r["id"]] = r
        for ch in r["name"].replace(" ", ""):
            db._name_index.setdefault(ch, set()).add(r["id"])
    return db


@pytest.fixture
def mock_inverted_index(sample_recipes):
    from matching.inverted_index import InvertedIndex
    idx = InvertedIndex()
    idx.build(sample_recipes)
    return idx
```

### 4.3 test_fuzzy_matcher.py

```python
"""FuzzyMatcher — 食材归一化 + 别名匹配"""
import pytest
from matching.fuzzy_matcher import FuzzyMatcher, INGREDIENT_SYNONYMS


class TestNormalize:
    def test_strip_whitespace(self):
        assert FuzzyMatcher.normalize("  鸡蛋  ") == "鸡蛋"

    def test_remove_modifier_prefix(self):
        assert FuzzyMatcher.normalize("有机西兰花") == "西兰花"
        assert FuzzyMatcher.normalize("进口牛奶") == "牛奶"

    def test_remove_unit_suffix(self):
        assert FuzzyMatcher.normalize("鸡蛋6个") == "鸡蛋"
        assert FuzzyMatcher.normalize("牛奶500ml") == "牛奶"

    def test_remove_gram_suffix(self):
        assert FuzzyMatcher.normalize("鸡胸肉500g") == "鸡胸肉"

    def test_lowercase(self):
        assert FuzzyMatcher.normalize("Egg") == "egg"

    def test_remove_trailing_digits(self):
        assert FuzzyMatcher.normalize("鸡蛋3") == "鸡蛋"


class TestIsMatch:
    def test_exact_match(self):
        assert FuzzyMatcher.is_match({"name": "鸡蛋"}, {"鸡蛋", "西红柿"})

    def test_synonym_match(self):
        assert FuzzyMatcher.is_match({"name": "番茄"}, {"西红柿", "鸡蛋"})
        assert FuzzyMatcher.is_match({"name": "西红柿"}, {"番茄", "鸡蛋"})

    def test_substring_match(self):
        assert FuzzyMatcher.is_match({"name": "鸡胸肉"}, {"鸡胸", "鸡蛋"})

    def test_no_match(self):
        assert not FuzzyMatcher.is_match({"name": "牛肉"}, {"鸡蛋", "西红柿"})

    def test_alias_match(self):
        assert FuzzyMatcher.is_match(
            {"name": "猪肉", "aliases": ["五花肉"]}, {"五花肉", "鸡蛋"})


class TestNormalizeFridgeItems:
    def test_basic_normalization(self):
        result = FuzzyMatcher.normalize_fridge_items([
            {"name": "鸡蛋", "cat": "肉蛋"}, {"name": "有机西红柿", "cat": "蔬菜"}])
        assert "鸡蛋" in result
        assert "西红柿" in result

    def test_synonym_expansion(self):
        result = FuzzyMatcher.normalize_fridge_items([{"name": "番茄", "cat": "蔬菜"}])
        assert "西红柿" in result

    def test_empty(self):
        assert FuzzyMatcher.normalize_fridge_items([]) == set()


class TestSynonyms:
    def test_symmetry(self):
        for key, syns in INGREDIENT_SYNONYMS.items():
            for s in syns:
                assert s in INGREDIENT_SYNONYMS, f"非对称: {key}→{s}"
                assert key in INGREDIENT_SYNONYMS[s], f"非对称: {s}→{key}"

    def test_no_self_reference(self):
        for key, syns in INGREDIENT_SYNONYMS.items():
            assert key not in syns, f"自引用: {key}"
```

### 4.4 test_inverted_index.py

```python
"""InvertedIndex — 食材→菜谱 O(1) 查找"""
import pytest
from matching.inverted_index import InvertedIndex


class TestInvertedIndex:
    def test_build_and_lookup(self, sample_recipes):
        idx = InvertedIndex(); idx.build(sample_recipes)
        result = idx.lookup("鸡蛋")
        assert "r001" in result and "r003" in result
        assert "r002" not in result

    def test_lookup_nonexistent(self, sample_recipes):
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert idx.lookup("不存在食材") == set()

    def test_fuzzy_lookup(self, sample_recipes):
        idx = InvertedIndex(); idx.build(sample_recipes)
        result = idx.fuzzy_lookup({"鸡蛋", "鸡胸肉"})
        assert result == {"r001", "r002", "r003"}

    def test_fuzzy_lookup_substring(self, sample_recipes):
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert "r002" in idx.fuzzy_lookup({"鸡胸"})

    def test_fuzzy_lookup_empty(self, sample_recipes):
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert idx.fuzzy_lookup(set()) == set()

    def test_synonym_during_build(self):
        recipes = [{"id": "t1", "name": "t", "ingredients": [{"name": "番茄"}]}]
        idx = InvertedIndex(); idx.build(recipes)
        assert "t1" in idx.fuzzy_lookup({"西红柿"})

    def test_len(self, sample_recipes):
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert len(idx) > 0
```

### 4.5 test_recipe_database.py

```python
"""RecipeDatabase — 菜谱 CRUD"""
import pytest


class TestRecipeDatabase:
    def test_get_existing(self, mock_recipe_db):
        r = mock_recipe_db.get("r001")
        assert r["name"] == "番茄炒蛋" and r["difficulty"] == "简单"

    def test_get_nonexistent(self, mock_recipe_db):
        assert mock_recipe_db.get("nonexistent") is None

    def test_all_count(self, mock_recipe_db):
        assert len(mock_recipe_db.all()) == 3

    def test_search_names_exact(self, mock_recipe_db):
        assert "r001" in mock_recipe_db.search_names("番茄炒蛋")

    def test_search_names_partial(self, mock_recipe_db):
        assert "r002" in mock_recipe_db.search_names("宫保")

    def test_search_names_no_match(self, mock_recipe_db):
        assert mock_recipe_db.search_names("佛跳墙") == []

    def test_len(self, mock_recipe_db):
        assert len(mock_recipe_db) == 3

    def test_fields_are_strings(self, mock_recipe_db):
        """Fix #9: difficulty/time 等字段必须是 str"""
        for r in mock_recipe_db.all():
            assert isinstance(r.get("difficulty"), str)
            assert isinstance(r.get("time"), str)
            assert isinstance(r.get("category"), str)
```

### 4.6 test_tools.py

```python
"""8个 @tool 函数 — mock 隔离外部依赖"""
import json, pytest
from unittest.mock import MagicMock, patch


class TestGetFridgeInventory:
    def test_empty(self):
        from api.tools import get_fridge_inventory, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(current_inventory=[], user_id="u1")
        assert json.loads(get_fridge_inventory(runtime))["status"] == "empty"

    def test_with_items(self, sample_inventory):
        from api.tools import get_fridge_inventory, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(current_inventory=sample_inventory, user_id="u1")
        r = json.loads(get_fridge_inventory(runtime))
        assert r["status"] == "ok" and r["total_items"] == 12


class TestSearchRecipesByIngredients:
    def test_match_found(self, mock_recipe_db, mock_inverted_index):
        with patch("api.tools.recipe_db", mock_recipe_db), \
             patch("api.tools.inverted_index", mock_inverted_index):
            from api.tools import search_recipes_by_ingredients
            r = json.loads(search_recipes_by_ingredients(["鸡蛋", "西红柿"]))
            assert any("番茄炒蛋" == x["name"] for x in r)

    def test_no_match(self, mock_recipe_db, mock_inverted_index):
        with patch("api.tools.recipe_db", mock_recipe_db), \
             patch("api.tools.inverted_index", mock_inverted_index):
            from api.tools import search_recipes_by_ingredients
            assert "未找到" in search_recipes_by_ingredients(["不存在的食材XYZ"])


class TestGetRecipeDetail:
    def test_existing(self, mock_recipe_db):
        with patch("api.tools.recipe_db", mock_recipe_db):
            from api.tools import get_recipe_detail
            r = json.loads(get_recipe_detail("r001"))
            assert r["name"] == "番茄炒蛋" and len(r["steps"]) > 0

    def test_nonexistent(self, mock_recipe_db):
        with patch("api.tools.recipe_db", mock_recipe_db):
            from api.tools import get_recipe_detail
            assert "error" in json.loads(get_recipe_detail("nope"))


class TestRecommendByFridge:
    def test_dietary_filter(self, mock_recipe_db, mock_inverted_index):
        from api.tools import recommend_by_fridge, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(
            current_inventory=[
                {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
                {"name": "鸡胸肉", "qty": 2, "cat": "肉蛋生鲜类"},
                {"name": "花生", "qty": 1, "cat": "包装食品类"},
            ],
            user_preferences={"忌口": ["花生"]}, user_id="u1")
        with patch("api.tools.recipe_db", mock_recipe_db), \
             patch("api.tools.inverted_index", mock_inverted_index):
            r = json.loads(recommend_by_fridge(runtime))
            names = [x["name"] for x in r.get("recipes", [])]
            assert "宫保鸡丁" not in names  # 含花生被过滤

    def test_match_sorting(self, mock_recipe_db, mock_inverted_index):
        from api.tools import recommend_by_fridge, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(
            current_inventory=[
                {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
                {"name": "牛奶", "qty": 1, "cat": "饮料乳品类"},
            ], user_preferences={}, user_id="u1")
        with patch("api.tools.recipe_db", mock_recipe_db), \
             patch("api.tools.inverted_index", mock_inverted_index):
            r = json.loads(recommend_by_fridge(runtime))
            recipes = r.get("recipes", [])
            if len(recipes) >= 2:
                assert recipes[0]["match_count"] >= recipes[1]["match_count"]


class TestSaveGetPreferences:
    def test_save_and_get(self):
        from api.tools import save_user_preferences, get_user_preferences, FridgeContext
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        r1 = MagicMock(); r1.store = store
        r1.context = FridgeContext(user_id="u_test")
        r = json.loads(save_user_preferences({"忌口": ["花生"]}, r1))
        assert r["status"] == "ok"

        r2 = MagicMock(); r2.store = store
        r2.context = FridgeContext(user_preferences={}, user_id="u_test")
        r = json.loads(get_user_preferences(r2))
        assert r["preferences"]["忌口"] == ["花生"]

    def test_merge_existing(self):
        from api.tools import save_user_preferences, FridgeContext
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        ctx = FridgeContext(user_id="u_test")
        r1 = MagicMock(); r1.store = store; r1.context = ctx
        save_user_preferences({"忌口": ["花生"]}, r1)
        r2 = MagicMock(); r2.store = store; r2.context = ctx
        r = json.loads(save_user_preferences({"人数": 3}, r2))
        assert r["saved"]["忌口"] == ["花生"] and r["saved"]["人数"] == 3
```

### 4.7 test_models.py

```python
"""Pydantic 模型验证"""
import pytest
from api.models import (
    RecipeSummary, RecipeDetail,
    AgentRecommendResponse, AgentRecipeItem,
    AgentSubstitutionResponse, AgentSubstitutionItem,
)


class TestRecipeModels:
    def test_summary_defaults(self):
        r = RecipeSummary(id="r001", name="测试")
        assert r.category == "其他" and r.difficulty == "未知"

    def test_detail_creation(self):
        r = RecipeDetail(id="r001", name="番茄炒蛋",
                         ingredients=[{"name": "鸡蛋"}], steps=["打蛋", "炒"])
        assert len(r.steps) == 2 and r.tips == ""


class TestAgentStructuredOutput:
    def test_recommend_response(self):
        resp = AgentRecommendResponse(
            recommendations=[
                AgentRecipeItem(name="番茄炒蛋", match_count=2, total_ingredients=2,
                                missing=[], difficulty="简单", time="15分钟")],
            fridge_summary="冰箱有4种食材")
        assert len(resp.recommendations) == 1
        assert "番茄炒蛋" in resp.model_dump_json()

    def test_substitution_response(self):
        resp = AgentSubstitutionResponse(
            suggestions=[
                AgentSubstitutionItem(
                    original="黄油", alternatives=["橄榄油", "椰子油"],
                    impact="口味略有变化")],
            summary="可用橄榄油替代")
        assert resp.suggestions[0].original == "黄油"
```

### 4.8 test_context_propagation.py

```python
"""FridgeContext → ToolRuntime 传播 + Middleware 配置"""
from unittest.mock import MagicMock


class TestFridgeContext:
    def test_defaults(self):
        from api.tools import FridgeContext
        ctx = FridgeContext()
        assert ctx.user_id == "default" and ctx.current_inventory == []

    def test_tool_runtime_reads_context(self):
        from api.tools import get_fridge_inventory, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(
            current_inventory=[{"name": "鸡蛋", "qty": 1, "cat": "肉蛋"}], user_id="u1")
        import json
        r = json.loads(get_fridge_inventory(runtime))
        assert r["items"][0]["name"] == "鸡蛋"


class TestMiddlewareConfig:
    def test_agent_creation_all_modes(self):
        from main import create_fridge_agent
        from langgraph.store.memory import InMemoryStore
        from langgraph.checkpoint.memory import InMemorySaver
        for mode in ["basic", "context", "subagents"]:
            agent = create_fridge_agent(
                agent_mode=mode, store=InMemoryStore(), checkpointer=InMemorySaver())
            assert agent is not None
```

---

## 五、Layer 2: RAG 检索与生成 — Ragas

> ContextPrecision(≥0.60) / ContextRecall(≥0.50) / Faithfulness(≥0.70) / AnswerRelevancy(≥0.60) / AnswerCorrectness(≥0.50)

### 5.1 评测数据集 (`tests/rag/eval_data/rag_eval_dataset.json`)

```json
[
  {"question": "如何让鸡肉更嫩？", "ground_truth": "腌制时加入淀粉和蛋清，控制火候不要过老"},
  {"question": "番茄炒蛋需要哪些食材？", "ground_truth": "鸡蛋、番茄、葱、盐、糖"},
  {"question": "川菜有什么特点？", "ground_truth": "以麻辣为主，善用辣椒花椒，代表菜有宫保鸡丁、麻婆豆腐"},
  {"question": "煎鱼怎么不粘锅？", "ground_truth": "锅要烧热再放油，鱼身擦干水分，中火煎至定型再翻面"},
  {"question": "怎样挑选新鲜的鸡蛋？", "ground_truth": "看蛋壳是否粗糙有光泽，摇晃无声，放入水中沉底为新鲜"},
  {"question": "宫保鸡丁的烹饪步骤？", "ground_truth": "鸡胸肉切丁腌制，花生炸脆，干辣椒花椒爆香，炒鸡丁，加调料，最后放花生"},
  {"question": "做红烧肉需要什么调料？", "ground_truth": "生抽、老抽、冰糖、料酒、八角、桂皮、姜、葱"},
  {"question": "鸡蛋和番茄能做什么菜？", "ground_truth": "番茄炒蛋、番茄蛋花汤、番茄鸡蛋面"},
  {"question": "牛奶可以做什么甜品？", "ground_truth": "双皮奶、牛奶炖蛋、姜撞奶、牛奶布丁"},
  {"question": "猪肉不同部位怎么烹饪？", "ground_truth": "里脊适合快炒，五花肉适合红烧，排骨适合炖汤"},
  {"question": "如何去除羊肉的膻味？", "ground_truth": "用料酒、姜片、花椒水浸泡，焯水时加白萝卜或茶叶"},
  {"question": "米饭和什么一起炒最好吃？", "ground_truth": "蛋炒饭、扬州炒饭（加火腿虾仁青豆）、酱油炒饭"},
  {"question": "新手适合做什么菜？", "ground_truth": "番茄炒蛋、拍黄瓜、蒸水蛋、清炒时蔬等简单快手菜"},
  {"question": "糖醋排骨怎么做？", "ground_truth": "排骨焯水，调糖醋汁，先炸后烧，收汁即可"},
  {"question": "蔬菜如何保持翠绿？", "ground_truth": "焯水时加盐和油，焯水后立即过冷水，炒制时大火快炒"}
]
```

### 5.2 test_retrieval_ragas.py

```python
"""Ragas RAG 检索质量测试"""
import os, json, pytest
from pathlib import Path
from datasets import Dataset


def load_eval_dataset() -> Dataset:
    path = Path(__file__).parent / "eval_data" / "rag_eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return Dataset.from_list(json.load(f))


def get_eval_llm():
    from langchain.chat_models import init_chat_model
    return init_chat_model(
        f"openai:{os.getenv('EVAL_MODEL', 'deepseek-v4-flash')}",
        temperature=0.0, max_tokens=512,
        openai_api_key=os.getenv("EVAL_API_KEY"),
        openai_api_base=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"))


def get_eval_embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5",
                                  model_kwargs={"device": "cpu"})


def run_rag_query(question: str) -> dict:
    from api.dependencies import rag_system
    if not rag_system or not rag_system.system_ready:
        pytest.skip("RAG system not initialized")
    result, analysis = rag_system.ask_question_with_routing(question, stream=False)
    contexts = []
    if analysis and hasattr(analysis, 'relevant_docs'):
        contexts = [d.page_content for d in analysis.relevant_docs]
    return {
        "question": question,
        "answer": result if isinstance(result, str) else str(result),
        "contexts": contexts,
        "route_strategy": analysis.recommended_strategy.value if analysis else "unknown",
    }


class TestRAGRetrieval:
    @pytest.mark.rag
    @pytest.mark.slow
    def test_context_precision(self):
        from ragas.metrics import ContextPrecision
        from ragas import evaluate
        ds = load_eval_dataset()
        results = [run_rag_query(q) for q in ds["question"]]
        ds = ds.add_column("contexts", [r["contexts"] for r in results])
        score = evaluate(ds, metrics=[ContextPrecision()],
                         llm=get_eval_llm(), embeddings=get_eval_embeddings())
        cp = score["context_precision"]
        print(f"\n  ContextPrecision: {cp:.4f} (目标 >= 0.60)")
        assert cp >= 0.50, f"{cp:.4f} < 0.50"

    @pytest.mark.rag
    @pytest.mark.slow
    def test_route_distribution(self):
        ds = load_eval_dataset()
        results = [run_rag_query(q) for q in ds["question"]]
        strategies = [r["route_strategy"] for r in results]
        print(f"\n  路由分布: { {s: strategies.count(s) for s in set(strategies)} }")
        assert len(set(strategies)) >= 1


class TestRAGGeneration:
    @pytest.mark.rag
    @pytest.mark.slow
    def test_comprehensive(self):
        """一键运行全部 5 个 Ragas 指标"""
        from ragas.metrics import (
            ContextPrecision, ContextRecall, Faithfulness,
            AnswerRelevancy, AnswerCorrectness)
        from ragas import evaluate

        ds = load_eval_dataset()
        results = [run_rag_query(q) for q in ds["question"]]
        ds = ds.add_column("answer", [r["answer"] for r in results])
        ds = ds.add_column("contexts", [r["contexts"] for r in results])

        score = evaluate(
            ds,
            metrics=[ContextPrecision(), ContextRecall(), Faithfulness(),
                     AnswerRelevancy(), AnswerCorrectness()],
            llm=get_eval_llm(), embeddings=get_eval_embeddings())

        thresholds = {
            "context_precision": 0.50, "context_recall": 0.40,
            "faithfulness": 0.60, "answer_relevancy": 0.50,
            "answer_correctness": 0.40,
        }

        print("\n" + "=" * 60)
        print("  RAG 综合评测 (Ragas)")
        print("=" * 60)
        passed = 0
        for m, v in score.items():
            bar = "█" * int(v * 20)
            ok = v >= thresholds.get(m, 0)
            flag = "✓" if ok else "✗"
            print(f"  {flag} {m:<25s}: {v:.4f} {bar}")
            if ok: passed += 1
        print("=" * 60)
        print(f"  通过: {passed}/{len(thresholds)}")
        assert passed >= 3, f"仅 {passed}/{len(thresholds)} 项达标"
```

---

## 六、Layer 3: Agent 行为测试 — DeepEval

> ToolCorrectness ≥ 80% / TaskCompletion ≥ 80% / Subagent 路由正确

### 6.1 test_tool_selection_deepeval.py

```python
"""DeepEval Agent 工具选择 + 任务完成测试"""
import os, json, pytest
from deepeval import evaluate
from deepeval.metrics import ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase


AGENT_TEST_CASES = [
    # (用户请求, 预期工具, 预期关键信息, 类别)
    ("冰箱里有什么？", ["get_fridge_inventory"], ["食材"], "inventory"),
    ("能做什么菜？", ["recipe_expert"], ["推荐"], "recommend"),
    ("推荐几道家常菜", ["recipe_expert"], ["家常"], "recommend"),
    ("鸡蛋和西红柿能做什么？", ["recipe_expert"], ["番茄炒蛋"], "recommend"),
    ("番茄炒蛋怎么做？", ["recipe_expert"], ["鸡蛋", "步骤"], "detail"),
    ("没有黄油可以用什么代替？", ["substitution_expert"], ["替代"], "substitution"),
    ("家里没有料酒了，能用什么替代？", ["substitution_expert"], ["替代"], "substitution"),
    ("怎么让鸡肉更嫩？", ["cooking_expert"], ["腌制", "嫩"], "knowledge"),
    ("煎鱼不粘锅有什么技巧？", ["cooking_expert"], ["煎", "技巧"], "knowledge"),
    ("川菜有什么特点？", ["cooking_expert"], ["川菜", "麻辣"], "knowledge"),
    ("我不吃花生，对海鲜过敏", ["save_user_preferences"], ["保存"], "preferences"),
    ("我喜欢川菜，3个人吃饭", ["save_user_preferences"], ["保存"], "preferences"),
]


def get_eval_llm():
    from langchain.chat_models import init_chat_model
    return init_chat_model(
        f"openai:{os.getenv('EVAL_MODEL', 'deepseek-v4-flash')}",
        temperature=0.0, max_tokens=512,
        openai_api_key=os.getenv("EVAL_API_KEY"),
        openai_api_base=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"))


def run_agent_query(message: str) -> dict:
    from api.dependencies import fridge_agent
    from api.tools import FridgeContext
    import api.dependencies as deps
    if not fridge_agent:
        pytest.skip("Agent not initialized")
    deps.current_fridge_inventory = [
        {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"},
        {"name": "西红柿", "qty": 3, "cal": 18, "cat": "蔬菜"},
        {"name": "鸡胸肉", "qty": 2, "cal": 133, "cat": "肉蛋生鲜类"},
    ]
    ctx = FridgeContext(
        current_inventory=deps.current_fridge_inventory,
        user_preferences={"忌口": ["花生"]}, user_id="test_agent")
    result = fridge_agent.invoke(
        {"messages": [{"role": "user", "content": message}]}, context=ctx)
    messages = result.get("messages", [])
    tool_calls, final_answer = [], ""
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(tc.get("name", "unknown"))
        if hasattr(msg, "content") and msg.content:
            if not hasattr(msg, "tool_calls"):
                final_answer = msg.content
    return {"input": message, "tool_calls": tool_calls, "final_answer": final_answer}


class TestAgentToolSelection:
    @pytest.mark.agent
    @pytest.mark.slow
    @pytest.mark.parametrize("input_msg,expected_tools,_,cat", AGENT_TEST_CASES)
    def test_each(self, input_msg, expected_tools, _, cat):
        result = run_agent_query(input_msg)
        matched = set(expected_tools) & set(result["tool_calls"])
        print(f"\n  [{cat}] '{input_msg[:40]}' → {result['tool_calls']}")
        assert len(matched) > 0, f"预期 {expected_tools}, 实际 {result['tool_calls']}"

    @pytest.mark.agent
    @pytest.mark.slow
    def test_aggregate_accuracy(self):
        correct = 0
        for input_msg, expected, _, _ in AGENT_TEST_CASES:
            result = run_agent_query(input_msg)
            if set(expected) & set(result["tool_calls"]):
                correct += 1
        accuracy = correct / len(AGENT_TEST_CASES)
        print(f"\n  Agent 工具选择正确率: {correct}/{len(AGENT_TEST_CASES)} = {accuracy:.1%}")
        assert accuracy >= 0.70, f"{accuracy:.1%} < 70%"


class TestSubagentRouting:
    @pytest.mark.agent
    def test_recipe_to_expert(self):
        """菜谱类请求必须路由到 recipe_expert, 不能直接调基础 tool"""
        for q in ["能做什么菜", "红烧肉怎么做", "搜索川菜菜谱"]:
            result = run_agent_query(q)
            tools = result["tool_calls"]
            if tools:
                assert not {"recommend_by_fridge", "search_recipes_by_ingredients"}.issuperset(tools), \
                    f"'{q}' 应路由到 recipe_expert, 实际: {tools}"

    @pytest.mark.agent
    def test_knowledge_to_expert(self):
        """知识类请求路由到 cooking_expert"""
        for q in ["怎么让鸡肉更嫩", "煲汤要多久"]:
            result = run_agent_query(q)
            if result["tool_calls"]:
                assert "search_cooking_knowledge" not in result["tool_calls"], \
                    f"'{q}' 应路由到 cooking_expert, 实际: {result['tool_calls']}"
```

---

## 七、Layer 4: 集成测试 — pytest + TruLens

### 7.1 test_agent_invoke.py

```python
"""Agent/Graph 集成 — 真实 invoke (需 DeepSeek API)"""
import os, pytest
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver


@pytest.fixture(scope="module")
def test_graph():
    os.environ.setdefault("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    from main import create_fridge_graph_wrapper
    return create_fridge_graph_wrapper(store=InMemoryStore(), checkpointer=InMemorySaver())


class TestAgentInvoke:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_basic(self, test_graph):
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 3, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 2, "cat": "蔬菜"}]
        r = test_graph.invoke(
            {"messages": [{"role": "user", "content": "你好，推荐一道菜"}]},
            config={"configurable": {"thread_id": "test_basic"}})
        assert len(r["messages"]) > 0
        print(f"\n  {r['messages'][-1].content[:200]}")

    @pytest.mark.integration
    @pytest.mark.slow
    def test_inventory(self, test_graph):
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"}]
        r = test_graph.invoke(
            {"messages": [{"role": "user", "content": "冰箱里有什么？"}]},
            config={"configurable": {"thread_id": "test_inv"}})
        content = r["messages"][-1].content.lower()
        assert "鸡蛋" in content or "egg" in content


class TestGraphMultiTurn:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_two_turns(self, test_graph):
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"}]
        cfg = {"configurable": {"thread_id": "test_mt_001"}}
        r1 = test_graph.invoke(
            {"messages": [{"role": "user", "content": "推荐一道菜"}]}, config=cfg)
        r2 = test_graph.invoke(
            {"messages": [{"role": "user", "content": "具体步骤是什么？"}]}, config=cfg)
        assert len(r2["messages"]) > len(r1["messages"])

    @pytest.mark.integration
    @pytest.mark.slow
    def test_thread_isolation(self, test_graph):
        test_graph.invoke(
            {"messages": [{"role": "user", "content": "我叫张三"}]},
            config={"configurable": {"thread_id": "user_a"}})
        r_b = test_graph.invoke(
            {"messages": [{"role": "user", "content": "我是谁？"}]},
            config={"configurable": {"thread_id": "user_b"}})
        assert "张三" not in r_b["messages"][-1].content
```

### 7.2 test_trulens_feedback.py

```python
"""TruLens 反馈函数 — LLM-as-Judge"""
import os, pytest


def get_provider():
    from trulens.providers.openai import OpenAIProvider
    return OpenAIProvider(
        model=f"openai:{os.getenv('EVAL_MODEL', 'deepseek-v4-flash')}",
        api_key=os.getenv("EVAL_API_KEY"),
        base_url=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"))


class TestTruLens:
    @pytest.mark.integration
    @pytest.mark.slow
    def test_groundedness(self):
        from trulens.feedback import Groundedness
        g = Groundedness(provider=get_provider())
        scores = []
        for source, response in [
            ("番茄炒蛋需要鸡蛋2个、番茄2个。步骤: 打蛋→炒蛋→炒番茄→混合调味。",
             "番茄炒蛋做法: 先打两个鸡蛋炒熟盛出, 再炒番茄至出汁, 最后混合调味即可。"),
            ("新鲜鸡蛋蛋壳粗糙有光泽，摇晃无声音，放入水中沉底。",
             "挑选鸡蛋要看蛋壳是否粗糙有光泽，摇晃检查是否无声，放入水中会沉底的就是新鲜鸡蛋。"),
        ]:
            s = g(source=source, statement=response)
            scores.append(s)
            print(f"  Groundedness: {s:.4f}")
        avg = sum(scores) / len(scores)
        print(f"\n  平均 Groundedness: {avg:.4f} (目标 >= 0.6)")
        assert avg >= 0.5

    @pytest.mark.integration
    @pytest.mark.slow
    def test_relevance(self):
        from trulens.feedback import Relevance
        r = Relevance(provider=get_provider())
        scores = []
        for prompt, response in [
            ("鸡蛋和番茄能做什么菜？",
             "鸡蛋和番茄最经典的搭配是番茄炒蛋，还可以做番茄蛋花汤、番茄鸡蛋面。"),
            ("煎鱼怎么不粘锅？",
             "锅烧热再放油，鱼身擦干水分，下锅后不要急着翻动，中火煎至定型再翻面。"),
        ]:
            s = r(prompt=prompt, response=response)
            scores.append(s)
            print(f"  Relevance: {s:.4f}")
        avg = sum(scores) / len(scores)
        print(f"\n  平均 Relevance: {avg:.4f} (目标 >= 0.6)")
        assert avg >= 0.5
```

---

## 八、Layer 5: 端到端测试 — pytest-asyncio

### 8.1 test_full_conversation.py

```python
"""E2E — 完整对话流程"""
import os, pytest
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver


@pytest.fixture(scope="module")
def e2e_graph():
    os.environ.setdefault("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    from main import create_fridge_graph_wrapper
    return create_fridge_graph_wrapper(store=InMemoryStore(), checkpointer=InMemorySaver())


class TestFullConversation:
    @pytest.mark.e2e
    @pytest.mark.slow
    def test_recommend_then_detail(self, e2e_graph):
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"},
            {"name": "鸡胸肉", "qty": 2, "cat": "肉蛋生鲜类"}]
        cfg = {"configurable": {"thread_id": "e2e_001"}}
        r1 = e2e_graph.invoke(
            {"messages": [{"role": "user", "content": "推荐一道简单的菜"}]}, config=cfg)
        r2 = e2e_graph.invoke(
            {"messages": [{"role": "user", "content": "完整步骤是什么？"}]}, config=cfg)
        assert len(r2["messages"]) > len(r1["messages"])
        print(f"\n  Turn1: {r1['messages'][-1].content[:150]}")
        print(f"  Turn2: {r2['messages'][-1].content[:150]}")

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_substitution_flow(self, e2e_graph):
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"}]
        cfg = {"configurable": {"thread_id": "e2e_sub"}}
        r1 = e2e_graph.invoke(
            {"messages": [{"role": "user", "content": "鸡蛋西红柿能做什么菜？"}]}, config=cfg)
        r2 = e2e_graph.invoke(
            {"messages": [{"role": "user", "content": "没有鸡蛋可以用什么代替？"}]}, config=cfg)
        assert len(r2["messages"][-1].content) > 20
        print(f"\n  Recommend: {r1['messages'][-1].content[:150]}")
        print(f"  Substitute: {r2['messages'][-1].content[:150]}")

    @pytest.mark.e2e
    @pytest.mark.slow
    def test_cooking_knowledge(self, e2e_graph):
        import api.dependencies as deps
        deps.current_fridge_inventory = []
        r = e2e_graph.invoke(
            {"messages": [{"role": "user", "content": "煲汤一般要煲多久？有什么技巧？"}]},
            config={"configurable": {"thread_id": "e2e_know"}})
        assert len(r["messages"][-1].content) > 30
        print(f"\n  {r['messages'][-1].content[:300]}")
```

### 8.2 test_ws_chat.py

```python
"""WebSocket 协议测试"""
import json, pytest
from unittest.mock import MagicMock, AsyncMock


class TestWSProtocol:
    def test_chat_message_schema(self):
        msg = {"type": "chat", "message": "能做什么菜?", "thread_id": "u1"}
        assert json.loads(json.dumps(msg)) == msg

    def test_server_event_types(self):
        events = {"stream_token", "stream_tool_start", "stream_tool_end",
                  "stream_tool_error", "stream_interrupt", "stream_done",
                  "stream_error", "pong"}
        assert events  # 完整性检查


class TestChatRelayLogic:
    @pytest.mark.asyncio
    async def test_busy_guard(self):
        ws = MagicMock(); ws.send_json = AsyncMock(); ws._chat_busy = True
        if getattr(ws, '_chat_busy', False):
            await ws.send_json({"type": "stream_error",
                                "error": "上一条消息仍在处理中，请稍候"})
        assert "处理中" in ws.send_json.call_args[0][0]["error"]

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        ws = MagicMock(); ws.send_json = AsyncMock()
        if not "":
            await ws.send_json({"type": "stream_error", "error": "message 不能为空"})
        assert "不能为空" in ws.send_json.call_args[0][0]["error"]

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self):
        ws = MagicMock(); ws.send_json = AsyncMock()
        try:
            json.loads("not valid json {")
        except json.JSONDecodeError:
            await ws.send_json({"type": "stream_error", "error": "消息格式错误，需要 JSON"})
        assert "格式错误" in ws.send_json.call_args[0][0]["error"]
```

---

## 九、Layer 6: 提示词测试 — Promptfoo

### 9.1 导出 System Prompt (`tests/prompts/current_system_prompt.txt`)

```
你是「尝尝咸淡」智能冰箱管家，协调专业子 Agent 为用户服务。

你直属的能力:
1. 查看冰箱当前食材清单 (get_fridge_inventory)
2. 保存用户饮食偏好到长期记忆 (save_user_preferences)
3. 读取已保存的用户偏好 (get_user_preferences)

你可以调度的专家:
- recipe_expert (菜谱推荐专家): 推荐菜谱、搜索菜谱、查看做法
- substitution_expert (食材替换专家): 为缺少的食材找替代方案
- cooking_expert (烹饪知识专家): 回答烹饪技巧、食材知识

路由规则:
- 凡是涉及「推荐菜/做什么菜/搜索菜谱/菜的做法」→ 调用 recipe_expert
- 凡是涉及「代替/替换/缺XX怎么办」→ 调用 substitution_expert
- 凡是涉及「烹饪技巧/食材知识/怎么做更好吃」→ 调用 cooking_expert
- 问「冰箱里有什么」→ 调用 get_fridge_inventory
- 用户声明饮食偏好 → 调用 save_user_preferences

你的职责是理解用户需求 → 路由到对应专家 → 综合专家的回答返回给用户。
不要自己回答菜谱推荐、替换建议、烹饪知识类问题，交给专家处理。
```

### 9.2 promptfooconfig.yaml

```yaml
description: "FridgeAI System Prompt 评测"

providers:
  - id: openai:deepseek-v4-flash
    config:
      apiBaseUrl: https://api.deepseek.com/v1
      apiKey: ${DEEPSEEK_API_KEY}
      temperature: 0.1
      max_tokens: 1024
    label: current
    prompt:
      - role: system
        content: file://Backend/tests/prompts/current_system_prompt.txt
      - role: user
        content: "{{question}}"

defaultTest:
  assert:
    - type: not-icontains
      value: "无法回答"
    - type: javascript
      value: "output.length > 50 && output.length < 2000"

tests:
  - vars: {question: "能做什么菜？冰箱里有鸡蛋和西红柿"}
    assert:
      - type: icontains; value: "鸡蛋"
      - type: icontains; value: "番茄"

  - vars: {question: "没有黄油可以用什么代替？"}
    assert:
      - type: icontains; value: "替代"

  - vars: {question: "煎鱼怎么不粘锅？"}
    assert:
      - type: javascript; value: "output.length > 80"

  - vars: {question: "我对花生过敏，帮我记一下"}
    assert:
      - type: icontains; value: "花生"

  - vars: {question: "冰箱里现在有什么？"}
    assert:
      - type: javascript; value: "output.length > 20"

  - vars: {question: "你好"}
    assert:
      - type: javascript; value: "output.length > 5"
```

运行: `npx promptfoo eval -c Backend/tests/prompts/promptfooconfig.yaml`

---

## 十、Layer 7: 可观测性 — LangSmith

```python
"""LangSmith 回归数据集 (可选, 需 API Key)
运行: python Backend/tests/rag/create_langsmith_dataset.py
"""
import os


def create_regression_dataset():
    try:
        from langsmith import Client
        client = Client()
    except ImportError:
        print("LangSmith SDK not installed"); return

    ds_name = "fridgeai-regression-v1"
    existing = list(client.list_datasets(dataset_name=ds_name))
    if existing:
        print(f"Dataset '{ds_name}' exists"); return

    ds = client.create_dataset(ds_name)
    examples = [
        {"question": "鸡蛋和西红柿能做什么菜？",
         "expected_tools": ["recipe_expert"], "expected_keywords": ["番茄炒蛋"]},
        {"question": "推荐3道使用鸡胸肉的低脂菜",
         "expected_tools": ["recipe_expert"], "expected_keywords": ["鸡胸"]},
        {"question": "没有料酒可以用什么替代？",
         "expected_tools": ["substitution_expert"], "expected_keywords": ["替代"]},
        {"question": "怎么让炒青菜保持翠绿？",
         "expected_tools": ["cooking_expert"], "expected_keywords": ["焯水"]},
        {"question": "我不吃辣，帮我记住",
         "expected_tools": ["save_user_preferences"], "expected_keywords": ["保存"]},
    ]
    for ex in examples:
        client.create_example(
            inputs={"question": ex["question"]},
            outputs={"expected_tools": ex["expected_tools"],
                     "expected_keywords": ex["expected_keywords"]},
            dataset_id=ds.id)
    print(f"Created dataset: {ds_name} ({len(examples)} examples)")


if __name__ == "__main__":
    create_regression_dataset()
```

---

## 十一、测试数据准备

### 冰箱食材场景 (`tests/test_data/`)

| 场景 | 食材 | 用途 |
|------|------|------|
| INVENTORY_RICH | 鸡蛋x6 + 西红柿x3 + 鸡胸肉x2 + 牛奶x1 + 青椒x4 + 洋葱x2 | 正常推荐 |
| INVENTORY_MINIMAL | 鸡蛋x2 | 少量食材边界 |
| INVENTORY_EMPTY | [] | 空冰箱边界 |
| INVENTORY_SYNONYMS | 番茄x3 + 马铃薯x4 + 生抽x1 | 同义词匹配 |
| INVENTORY_RAW_NAMES | 有机鸡蛋500g + 进口牛奶1L + 鲜西红柿 | 归一化验证 |

### Agent 测试场景覆盖

| 类别 | 数量 | 示例 |
|------|------|------|
| greeting | 3 | "你好"、"你能做什么？" |
| inventory | 3 | "冰箱里有什么？" |
| recommend_by_fridge | 4 | "能做什么菜？"、"今晚吃什么好？" |
| recommend_by_ingredients | 3 | "鸡蛋和西红柿能做什么？" |
| recipe_detail | 3 | "番茄炒蛋怎么做？" |
| substitution | 3 | "没有黄油可以用什么代替？" |
| cooking_knowledge | 5 | "怎么让鸡肉更嫩？"、"川菜有什么特点？" |
| preferences | 5 | "我对花生过敏"、"记住我喜欢川菜" |
| mixed | 3 | "推荐川菜并告诉做法" |
| edge_cases | 4 | ""、"???"、"帮我做不存在的菜XYZ" |

---

## 十二、CI/CD 集成 — GitHub Actions

**`.github/workflows/test.yml`:**

```yaml
name: FridgeAI Tests

on:
  push: {branches: [main], paths: ['Backend/**']}
  pull_request: {branches: [main], paths: ['Backend/**']}

env:
  PYTHON_VERSION: '3.12'
  DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}

jobs:
  unit-tests:
    name: Unit Tests (Fast)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '${{ env.PYTHON_VERSION }}'}
      - run: pip install pytest pytest-cov pytest-mock pydantic langchain langchain-core langgraph
      - name: Run unit tests
        working-directory: Backend
        run: python -m pytest tests/unit/ -v --tb=short --cov=. --cov-report=xml -m unit
      - uses: codecov/codecov-action@v4
        with: {file: Backend/coverage.xml}

  rag-eval:
    name: RAG Evaluation (Ragas)
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '${{ env.PYTHON_VERSION }}'}
      - run: pip install ragas datasets pandas langchain langchain-openai langchain-huggingface sentence-transformers
      - name: Run RAG eval
        working-directory: Backend
        env:
          EVAL_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          EVAL_API_BASE: https://api.deepseek.com/v1
        run: python -m pytest tests/rag/ -v --tb=long -m rag --timeout=300 --junitxml=rag-results.xml

  agent-eval:
    name: Agent Evaluation (DeepEval)
    runs-on: ubuntu-latest
    needs: unit-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '${{ env.PYTHON_VERSION }}'}
      - run: pip install deepeval langchain langchain-openai langgraph
      - name: Run Agent eval
        working-directory: Backend
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          EVAL_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          EVAL_API_BASE: https://api.deepseek.com/v1
        run: python -m pytest tests/agent/ -v --tb=long -m agent --timeout=300

  prompt-eval:
    name: Prompt Evaluation
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: '20'}
      - env: {DEEPSEEK_API_KEY: '${{ secrets.DEEPSEEK_API_KEY }}'}
        run: npx promptfoo eval -c Backend/tests/prompts/promptfooconfig.yaml --max-concurrency 2
```

---

## 十三、测试报告模板

### 运行命令

```bash
# 分层运行
cd Backend
python -m pytest tests/unit/ -v -m unit                          # < 5s
python -m pytest tests/rag/ -v -m rag --timeout=300              # ~30s
python -m pytest tests/agent/ -v -m agent --timeout=300          # ~30s
python -m pytest tests/integration/ -v -m integration --timeout=300  # ~60s
python -m pytest tests/e2e/ -v -m e2e --timeout=300              # ~120s

# 一键全量 (跳过 LLM)
python -m pytest tests/unit/ -v -m unit

# 覆盖率
python -m pytest tests/unit/ --cov=. --cov-report=html
```

### 报告模板

```markdown
# FridgeAI 测试报告 — YYYY-MM-DD

## 摘要

| 指标 | 本次 | 基线 | 趋势 |
|------|------|------|------|
| 单元测试覆盖率 | XX% | 70% | → |
| RAG Faithfulness | X.XX | 0.70 | → |
| RAG ContextPrecision | X.XX | 0.60 | → |
| Agent 工具选择正确率 | XX% | 80% | → |
| Agent 任务完成率 | XX% | 80% | → |
| Prompt 断言通过率 | XX% | 100% | → |

## 分层结果

### Layer 1: 单元测试 — __/__ 通过, 覆盖率 __%

### Layer 2: RAG (Ragas)
- ContextPrecision: ____ | ContextRecall: ____ | Faithfulness: ____
- AnswerRelevancy: ____ | AnswerCorrectness: ____

### Layer 3: Agent (DeepEval)
- ToolCorrectness: ____ | 工具选择: __/__ 通过

### Layer 4-5: 集成/E2E — __/__ 通过

### Layer 6: Promptfoo — __/__ 断言通过

## 发现问题

| ID | 严重度 | 描述 | 状态 |
|----|--------|------|------|
| 1 | | | |

## 签核
执行人: _____ 日期: _____
```

---

## 十四、验收检查清单

### Phase 0: 环境 (0.5 天)
- [ ] 全部测试框架安装成功
- [ ] `.env.test` 配置完成
- [ ] `Backend/tests/` 目录结构创建
- [ ] `python -m pytest tests/unit/ -v` 全通过

### Phase 1: 单元测试 (1 天)
- [ ] FuzzyMatcher: 12+ 用例全通过
- [ ] InvertedIndex: 7+ 用例全通过
- [ ] RecipeDatabase: 8+ 用例全通过
- [ ] Tools: 10+ 用例全通过
- [ ] Models: 6+ 用例全通过
- [ ] Context: 5+ 用例全通过
- [ ] 覆盖率 >= 60%

### Phase 2: RAG Ragas (1 天)
- [ ] 15 条标注数据准备完成
- [ ] ContextPrecision >= 0.50, ContextRecall >= 0.40
- [ ] Faithfulness >= 0.60, AnswerRelevancy >= 0.50
- [ ] 基线分数已记录

### Phase 3: Agent DeepEval (1 天)
- [ ] 12 条测试用例覆盖 8 类请求
- [ ] 工具选择正确率 >= 70%
- [ ] 子 Agent 路由验证通过

### Phase 4: 集成测试 (1 天)
- [ ] Agent invoke: 4 类请求全通过
- [ ] Graph 多轮: 2 场景通过
- [ ] TruLens: Groundedness >= 0.5, Relevance >= 0.5

### Phase 5: E2E + Prompt (1 天)
- [ ] 完整对话: 3 场景通过
- [ ] WebSocket 协议: 6 用例通过
- [ ] Promptfoo: 7 断言 >= 90% 通过

### Phase 6: CI/CD (0.5 天)
- [ ] GitHub Actions 正常运行
- [ ] PR 触发自动测试
- [ ] Artifacts 正确上传

---

## 附录 A: 框架版本兼容

| 框架 | 版本 | 注意 |
|------|------|------|
| pytest | >= 8.0 | 需 pytest-asyncio >= 0.23 |
| Ragas | >= 0.2.0 | 使用 evaluate() API |
| DeepEval | >= 2.0 | ToolCorrectnessMetric 2.x 稳定 |
| TruLens | >= 1.0 | 需 trulens-providers-langchain |
| Promptfoo | >= 0.80 | Node.js >= 18 |
| LangSmith | SDK >= 0.1 | 可选 |
| langgraph | 1.2.8 | 与项目一致 |

## 附录 B: 常见问题

**Q: Ragas evaluate() 报 "No LLM provided"** → 显式传 `llm=` 参数

**Q: 测试 LLM 超时** → 检查 `.env.test` 中 API Key/Base URL, 建议用 DeepSeek Flash

**Q: ModuleNotFoundError** → 在 `Backend/` 下运行或设 `PYTHONPATH=Backend`

**Q: Promptfoo Node.js 版本** → Node >= 18, 用 `npx promptfoo` 而非全局安装

**Q: CI 中 API Key** → GitHub Secrets → `DEEPSEEK_API_KEY`

## 附录 C: 成本估算

| 层 | LLM 调用 | Token 估算 | 成本 (DeepSeek) |
|----|----------|------------|------------------|
| Unit | 0 | 0 | $0 |
| Ragas (15题×5指标) | ~75 | ~75K | ~$0.01 |
| DeepEval (12题) | ~12 | ~12K | ~$0.002 |
| TruLens (5题) | ~10 | ~10K | ~$0.002 |
| Integration (8题) | ~8 | ~8K | ~$0.001 |
| E2E (4场景) | ~12 | ~12K | ~$0.002 |
| Promptfoo (9题×3) | ~27 | ~27K | ~$0.005 |
| **合计** | **~144** | **~144K** | **~$0.02** |

> 全量测试每次约 $0.02, 适合每次 PR。节约可降频 Agent/集成/E2E 层。

---

> **文档版本**: v4.0 | **创建**: 2026-07-09
>
> **实施路径**: 按 Phase 0→6 顺序执行, 优先 Phase 0-1 (无需 LLM, 可立即 CI 化)
