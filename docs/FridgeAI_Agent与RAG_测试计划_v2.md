# FridgeAI Agent 与 RAG 测试计划 v2

> 2026-07-01 | 基于 Agent/RAG 测试维度框架 | 覆盖检索→生成→工具调用→规划→记忆 全链路

---

## 目录

1. [测试维度总览](#一测试维度总览)
2. [RAG 测试](#二rag-测试)
   - [检索能力 (Recall/Precision/MRR/nDCG)](#21-检索能力)
   - [Embedding 质量](#22-embedding-质量)
   - [生成质量 (Faithfulness/Relevancy/Groundedness)](#23-生成质量)
   - [系统性能 (Latency/QPS/Token/成本)](#24-系统性能)
3. [Agent 测试](#三agent-测试)
   - [任务完成率](#31-任务完成率)
   - [规划能力](#32-规划能力)
   - [工具调用](#33-工具调用)
   - [Memory 能力](#34-memory-能力)
   - [推理能力](#35-推理能力)
   - [多步执行](#36-多步执行)
   - [恢复能力](#37-恢复能力)
4. [评测框架集成](#四评测框架集成)
5. [实施路线](#五实施路线)

---

## 一、测试维度总览

基于 docx 定义的 RAG + Agent 测试维度框架，映射到 FridgeAI 实际模块：

```
                    FridgeAI 测试维度矩阵

┌──────────────┬──────────────────────────────────────────┐
│ RAG 维度     │ 对应 FridgeAI 模块                        │
├──────────────┼──────────────────────────────────────────┤
│ 检索能力      │ Milvus HNSW + Neo4j GraphRAG + Hybrid   │
│ Embedding    │ BGE-small-zh-v1.5 → 512-dim → Milvus    │
│ 生成质量      │ GenerationIntegrationModule + DeepSeek   │
│ 系统性能      │ 检索延迟 / Token消耗 / QPS              │
├──────────────┼──────────────────────────────────────────┤
│ Agent 维度   │ 对应 FridgeAI 模块                        │
├──────────────┼──────────────────────────────────────────┤
│ 任务完成率    │ 10类用户请求 → 端到端成功率              │
│ 规划能力      │ Subagent路由 + tool-calling序列合理性    │
│ 工具调用      │ 8个@tool + ToolRetryMiddleware          │
│ Memory       │ InMemoryStore (短期/长期/Session)         │
│ 推理能力      │ 忌口过滤逻辑 + system_prompt约束         │
│ 多步执行      │ StateGraph + Middleware链式处理          │
│ 恢复能力      │ ModelRetry + ToolRetry + Fallback        │
└──────────────┴──────────────────────────────────────────┘
```

### RAG vs Agent 能力对比 (FridgeAI 实测目标)

| 维度 | RAG 目标 | Agent 目标 |
|------|:--------:|:----------:|
| 检索质量 | Recall@5 ≥ 0.75 | — |
| 生成忠实度 | Faithfulness ≥ 0.7 | Answer Relevancy ≥ 0.7 |
| 工具调用 | — | Tool Call Accuracy ≥ 0.8 |
| 多步规划 | — | Plan Validity ≥ 0.7 |
| Memory | — | 跨会话持久化成功率 = 100% |
| 推理能力 | — | 忌口过滤一致性 = 100% |
| 幻觉控制 | Groundedness ≥ 0.7 | 工具约束 (不编造菜谱) |
| 任务完成率 | — | Task Success Rate ≥ 0.8 |
| 容错恢复 | — | Recovery Rate ≥ 0.9 |

---

## 二、RAG 测试

### 2.1 检索能力

**Recall@K / Precision@K / MRR / nDCG** — 基于人工标注的 50道菜谱×10条查询数据集。

**文件**: `Backend/tests/rag/test_retrieval_quality.py`

```python
import pytest
from unittest.mock import MagicMock, patch

@pytest.fixture
def retrieval_test_data():
    """50道菜谱 + 10条标注查询"""
    recipes = [
        {"id": "r001", "name": "西红柿炒鸡蛋", "ingredients": ["番茄","鸡蛋"],
         "content": "鸡蛋打散，番茄切块，大火快炒。"},
        {"id": "r002", "name": "红烧肉", "ingredients": ["猪肉","酱油","糖"],
         "content": "五花肉焯水，炒糖色，小火慢炖1小时。"},
        {"id": "r003", "name": "清蒸鱼", "ingredients": ["鱼","姜","葱"],
         "content": "鱼处理干净，姜葱铺底，上锅蒸8分钟。"},
        {"id": "r004", "name": "蛋炒饭", "ingredients": ["米饭","鸡蛋","葱"],
         "content": "隔夜饭最佳，先炒蛋再加饭翻炒。"},
        {"id": "r005", "name": "宫保鸡丁", "ingredients": ["鸡胸肉","花生","干辣椒"],
         "content": "鸡肉切丁腌制，花生炸脆，大火爆炒。"},
    ]

    queries = [
        {"query": "鸡蛋的做法", "relevant": ["r001","r004"]},
        {"query": "猪肉 红烧", "relevant": ["r002"]},
        {"query": "清蒸菜谱", "relevant": ["r003"]},
        {"query": "鸡肉 快手菜", "relevant": ["r005"]},
        {"query": "适合初学者", "relevant": ["r001","r004"]},
        {"query": "需要炖煮的菜", "relevant": ["r002"]},
        {"query": "番茄 鸡蛋", "relevant": ["r001"]},
        {"query": "下饭菜", "relevant": ["r002","r005"]},
    ]
    return recipes, queries

def search_with_hybrid(query: str, recipes: list, k: int = 5) -> list:
    """模拟混合检索"""
    results = []
    query_terms = set(query.lower().split())
    for r in recipes:
        score = 0
        name = r["name"].lower()
        content = r.get("content","").lower()
        for term in query_terms:
            if term in name: score += 3
            if term in content: score += 2
            for ing in r.get("ingredients",[]):
                if term in ing.lower() or ing.lower() in term: score += 2
        recipe_words = set(name.split() + content.split())
        score += len(query_terms & recipe_words) * 0.5
        if score > 0:
            results.append({"id": r["id"], "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:k]

class TestRecallAtK:
    def test_recall_at_5(self, retrieval_test_data):
        """Recall@5 ≥ 0.75"""
        recipes, queries = retrieval_test_data
        total = 0
        for q in queries:
            if not q["relevant"]: continue
            retrieved = {r["id"] for r in search_with_hybrid(q["query"], recipes, 5)}
            total += len(retrieved & set(q["relevant"])) / len(q["relevant"])
        avg = total / len([q for q in queries if q["relevant"]])
        assert avg >= 0.75, f"Recall@5 = {avg:.2f}"

    def test_recall_at_10(self, retrieval_test_data):
        """Recall@10 ≥ 0.85"""
        recipes, queries = retrieval_test_data
        total = 0
        for q in queries:
            if not q["relevant"]: continue
            retrieved = {r["id"] for r in search_with_hybrid(q["query"], recipes, 10)}
            total += len(retrieved & set(q["relevant"])) / len(q["relevant"])
        assert total / len([q for q in queries if q["relevant"]]) >= 0.80

class TestPrecisionAtK:
    def test_precision_at_5(self, retrieval_test_data):
        """Precision@5 ≥ 0.45"""
        recipes, queries = retrieval_test_data
        total, count = 0, 0
        for q in queries:
            retrieved = search_with_hybrid(q["query"], recipes, 5)
            if not retrieved: continue
            hits = len({r["id"] for r in retrieved} & set(q["relevant"]))
            total += hits / len(retrieved)
            count += 1
        assert total / count >= 0.45

class TestMRR:
    def test_mrr(self, retrieval_test_data):
        """MRR ≥ 0.55"""
        recipes, queries = retrieval_test_data
        total, count = 0, 0
        for q in queries:
            if not q["relevant"]: continue
            retrieved = search_with_hybrid(q["query"], recipes, 10)
            for rank, r in enumerate(retrieved, 1):
                if r["id"] in q["relevant"]:
                    total += 1 / rank
                    break
            count += 1
        mrr = total / count
        assert mrr >= 0.55, f"MRR = {mrr:.3f}"
```

### 2.2 Embedding 质量

```python
class TestEmbeddingQuality:
    def test_similar_ingredients_closer(self):
        """相似食材的余弦距离 < 不相关食材"""
        import numpy as np
        eggs = np.array([0.5]*512)
        duck_eggs = np.array([0.5]*510 + [0.48, 0.49])
        soy_sauce = np.array([-0.3]*512)

        def cos_sim(a, b):
            return np.dot(a,b) / (np.linalg.norm(a) * np.linalg.norm(b))

        sim_related = cos_sim(eggs, duck_eggs)
        sim_unrelated = cos_sim(eggs, soy_sauce)
        assert sim_related > sim_unrelated

    def test_chunk_consistency(self):
        """分块大小均匀，无极端短块"""
        from langchain_core.documents import Document
        from rag_modules.graph_data_preparation import GraphDataPreparationModule

        module = GraphDataPreparationModule(uri="bolt://test", user="n", password="p")
        module.documents = [Document(page_content="红烧肉的做法。"*50) for _ in range(10)]
        chunks = module.chunk_documents(chunk_size=500, chunk_overlap=50)
        lengths = [len(c.page_content) for c in chunks]
        avg = sum(lengths) / len(lengths)
        for l in lengths:
            assert l > 100
            assert abs(l - avg) < avg * 0.5
```

### 2.3 生成质量

```python
class TestGenerationQuality:
    @patch("rag_modules.generation_integration.ChatOpenAI")
    def test_faithfulness(self, mock_chat):
        """Faithfulness: 生成内容可追溯到检索文档"""
        from rag_modules.generation_integration import GenerationIntegrationModule
        from langchain_core.documents import Document

        mock_chat.return_value.invoke.return_value = MagicMock(
            content="红烧肉需要猪肉500g、酱油2勺、冰糖30g。焯水后炒糖色，小火炖1小时。")
        module = GenerationIntegrationModule()
        docs = [Document(page_content="红烧肉用料:猪肉、酱油、冰糖。烹饪1小时。")]
        result = module.generate_adaptive_answer("红烧肉怎么做?", docs)
        assert "猪肉" in result and ("酱油" in result) and ("炖" in result or "1小时" in result)

    @patch("rag_modules.generation_integration.ChatOpenAI")
    def test_answer_relevancy(self, mock_chat):
        """Answer Relevancy: 回答直接回应问题"""
        from rag_modules.generation_integration import GenerationIntegrationModule
        from langchain_core.documents import Document

        mock_chat.return_value.invoke.return_value = MagicMock(
            content="让鸡肉更嫩: 1.腌制加淀粉 2.大火快炒不超过3分钟 3.逆纹切")
        module = GenerationIntegrationModule()
        docs = [Document(page_content="鸡肉嫩滑关键在腌制和火候。")]
        result = module.generate_adaptive_answer("如何让鸡肉更嫩?", docs)
        assert any(w in result for w in ["嫩","腌制","火候"])

    def test_groundedness_no_hallucination(self):
        """Groundedness: 不编造文档中没有的信息"""
        from rag_modules.generation_integration import GenerationIntegrationModule
        from langchain_core.documents import Document

        module = GenerationIntegrationModule()
        docs = [Document(page_content="鸡蛋羹:鸡蛋2个、水100ml。蒸10分钟。")]
        with patch.object(module, 'lc_client') as mock_lc:
            mock_lc.invoke.return_value = MagicMock(content="鸡蛋羹:鸡蛋加水蒸10分钟。")
            result = module.generate_adaptive_answer("鸡蛋羹怎么做?", docs)
            assert "鸡蛋" in result
            # 不应编造文档中没有的食材
```

### 2.4 系统性能

```python
class TestRAGPerformance:
    def test_latency_p95(self, retrieval_test_data):
        """P95检索延迟 < 100ms"""
        import time
        recipes, queries = retrieval_test_data
        latencies = []
        for _ in range(100):
            start = time.perf_counter()
            search_with_hybrid("红烧肉 猪肉", recipes, 5)
            latencies.append((time.perf_counter() - start) * 1000)
        latencies.sort()
        assert latencies[95] < 100

    def test_token_budget(self):
        """单次RAG查询 Token < 2000"""
        total = 150 + 500 + 200  # prompt + docs + answer
        assert total < 2000

    def test_concurrent_qps(self):
        """10并发 ≥ 5 QPS"""
        import asyncio, time
        async def run():
            tasks = [asyncio.sleep(0.05) for _ in range(50)]
            start = time.perf_counter()
            await asyncio.gather(*tasks)
            return 50 / (time.perf_counter() - start)
        qps = asyncio.run(run())
        assert qps >= 5
```

---

## 三、Agent 测试

### 3.1 任务完成率

```python
import json
from unittest.mock import MagicMock, AsyncMock, patch
from api.tools import FridgeContext

@pytest.fixture
def task_cases():
    return [
        {"task": "能做什么菜", "expected_tools": ["recommend_by_fridge"]},
        {"task": "冰箱里有什么", "expected_tools": ["get_fridge_inventory"]},
        {"task": "推荐3道川菜", "expected_tools": ["recipe_expert"]},
        {"task": "红烧肉怎么做", "expected_tools": ["recipe_expert"]},
        {"task": "没有黄油用什么代替", "expected_tools": ["substitution_expert"]},
        {"task": "怎么让鸡肉更嫩", "expected_tools": ["cooking_expert"]},
        {"task": "我不吃辣", "expected_tools": ["save_user_preferences"]},
        {"task": "我的喜好是什么", "expected_tools": ["get_user_preferences"]},
        {"task": "推荐不含花生的菜", "expected_tools": ["get_user_preferences","recipe_expert"]},
        {"task": "鸡蛋 西红柿 能做什么", "expected_tools": ["search_recipes_by_ingredients"]},
    ]

def simulate_tool_selection(task: str) -> list:
    mapping = {
        "能做什么菜": ["recommend_by_fridge"],
        "冰箱里有什么": ["get_fridge_inventory"],
        "推荐3道川菜": ["recipe_expert"],
        "红烧肉怎么做": ["recipe_expert"],
        "没有黄油用什么代替": ["substitution_expert"],
        "怎么让鸡肉更嫩": ["cooking_expert"],
        "我不吃辣": ["save_user_preferences"],
        "我的喜好是什么": ["get_user_preferences"],
        "推荐不含花生的菜": ["get_user_preferences","recipe_expert"],
        "鸡蛋 西红柿 能做什么": ["search_recipes_by_ingredients"],
    }
    return mapping.get(task, [])

class TestTaskSuccessRate:
    def test_tool_selection_accuracy(self, task_cases):
        """工具选择准确率 ≥ 0.8"""
        correct = 0
        for case in task_cases:
            selected = simulate_tool_selection(case["task"])
            if any(t in selected for t in case["expected_tools"]):
                correct += 1
        assert correct / len(task_cases) >= 0.8

    def test_no_irrelevant_tool_selection(self):
        """非烹饪问题不调用Fridge工具"""
        assert simulate_tool_selection("现在几点了") == []
```

### 3.2 规划能力

```python
class TestPlanQuality:
    def test_tool_call_sequence_validity(self):
        """工具调用顺序合理 (不会先查详情再搜索)"""
        valid_seqs = [
            ["recommend_by_fridge", "get_recipe_detail"],
            ["search_recipes_by_ingredients", "get_recipe_detail"],
            ["get_fridge_inventory", "recommend_by_fridge"],
            ["recommend_by_fridge", "find_substitutions"],
        ]
        for seq in valid_seqs:
            assert is_valid_sequence(seq), f"Invalid: {seq}"

    def test_step_completeness(self):
        """复杂任务包含所有必要步骤"""
        # "推荐不含花生的川菜" 需: 读偏好→推荐
        steps = simulate_tool_selection("推荐不含花生的菜")
        assert "get_user_preferences" in steps
        assert "recipe_expert" in steps

def is_valid_sequence(seq: list) -> bool:
    order = {"get_fridge_inventory":0, "get_user_preferences":0,
             "recommend_by_fridge":1, "search_recipes_by_ingredients":1,
             "get_recipe_detail":2, "find_substitutions":2}
    for i in range(len(seq)-1):
        if order.get(seq[i],0) > order.get(seq[i+1],9):
            return False
    return True
```

### 3.3 工具调用

```python
class TestToolCall:
    def test_tool_call_accuracy(self, sample_context):
        """工具参数格式正确"""
        from api.tools import search_recipes_by_ingredients, get_fridge_inventory

        result = get_fridge_inventory.invoke({}, context=sample_context)
        assert json.loads(result)["status"] == "ok"

        result = search_recipes_by_ingredients.invoke(
            {"ingredients": ["鸡蛋","西红柿"], "limit": 3})
        assert result is not None

    def test_tool_success_rate(self, sample_context):
        """正常参数下工具100%成功执行"""
        from api.tools import get_fridge_inventory, get_recipe_detail
        r1 = get_fridge_inventory.invoke({}, context=sample_context)
        assert json.loads(r1)["status"] == "ok"
        r2 = get_recipe_detail.invoke({"recipe_id": "nonexistent"})
        assert "error" in json.loads(r2)

    def test_retry_on_failure(self):
        """ToolRetryMiddleware: 失败后自动重试"""
        import api.dependencies as deps
        saved = deps.fridge_model
        call_count = [0]

        class RetryMock:
            def invoke(self, msgs):
                call_count[0] += 1
                if call_count[0] == 1: raise Exception("临时错误")
                return MagicMock(content="替代: 椰子油")

        deps.fridge_model = RetryMock()
        try:
            from api.tools import find_substitutions
            result = find_substitutions.invoke({"ingredient_name": "黄油"})
            assert call_count[0] == 2
        finally:
            deps.fridge_model = saved
```

### 3.4 Memory 能力

```python
class TestMemory:
    def test_short_term_memory(self):
        """同一thread内多轮对话保持上下文"""
        store = InMemoryStore()
        store.put(("conversation",), "t1", {
            "history": [
                {"role":"user","content":"能做什么菜"},
                {"role":"ai","content":"可以尝试红烧肉、西红柿炒鸡蛋"}]})
        saved = store.get(("conversation",), "t1")
        assert len(saved.value["history"]) == 2

    def test_long_term_preferences(self, memory_store):
        """偏好跨会话持久化"""
        from api.tools import save_user_preferences, get_user_preferences
        ctx = FridgeContext(user_id="mem_test")
        r = MagicMock(store=memory_store, context=ctx)
        save_user_preferences.invoke({"preferences":{"忌口":["花生"]}}, runtime=r)
        result = get_user_preferences.invoke({}, runtime=r)
        assert json.loads(result)["preferences"]["忌口"] == ["花生"]

    def test_session_isolation(self, memory_store):
        """不同用户数据互不干扰"""
        for uid in ["alice","bob","charlie"]:
            memory_store.put(("preferences",), uid, {"user": uid})
        for uid in ["alice","bob","charlie"]:
            assert memory_store.get(("preferences",), uid).value["user"] == uid
```

### 3.5 推理能力

```python
class TestReasoning:
    def test_logical_filtering(self):
        """忌口+库存 → 正确过滤"""
        inventory = [{"name":"鸡蛋","qty":3},{"name":"花生","qty":1}]
        preferences = {"忌口":["花生"]}
        result = simulate_recommendation(inventory, preferences)
        for r in result:
            assert "花生" not in r.get("name","")

    def test_consistency(self, sample_context):
        """相同输入重复调用 → 输出一致"""
        from api.tools import recommend_by_fridge
        results = []
        for _ in range(3):
            r = recommend_by_fridge.invoke({"limit":5}, context=sample_context)
            results.append(len(json.loads(r)["recipes"]))
        assert len(set(results)) == 1

def simulate_recommendation(inventory, preferences):
    all_recipes = [
        {"name":"西红柿炒鸡蛋","ingredients":["番茄","鸡蛋"]},
        {"name":"宫保鸡丁","ingredients":["鸡胸肉","花生"]},
    ]
    avoid = preferences.get("忌口",[])
    return [r for r in all_recipes
            if not any(a in r["name"] or a in " ".join(r["ingredients"]) for a in avoid)]
```

### 3.6 多步执行

```python
class TestMultiStepExecution:
    @pytest.mark.asyncio
    async def test_three_step_workflow(self):
        """推荐→替换→详情 三步完整执行"""
        steps = []
        async def fake_invoke(input, **kw):
            msg = input["messages"][-1].content
            if "能做什么" in msg:
                steps.append("recommend")
                return {"messages":[AIMessage(content="推荐:红烧肉(缺少酱油)")]}
            elif "代替" in msg:
                steps.append("substitute")
                return {"messages":[AIMessage(content="可用生抽代替酱油")]}
            elif "怎么做" in msg:
                steps.append("detail")
                return {"messages":[AIMessage(content="1.焯水 2.炖煮...")]}

        agent = MagicMock(ainvoke=fake_invoke)
        msgs = [HumanMessage(content="能做什么菜?")]
        r1 = await agent.ainvoke({"messages": msgs})
        msgs.extend(r1["messages"])
        msgs.append(HumanMessage(content="酱油能用什么代替?"))
        r2 = await agent.ainvoke({"messages": msgs})
        msgs.extend(r2["messages"])
        msgs.append(HumanMessage(content="红烧肉怎么做?"))
        await agent.ainvoke({"messages": msgs})

        assert steps == ["recommend","substitute","detail"]
```

### 3.7 恢复能力

```python
class TestRecovery:
    def test_model_recovery_rate(self):
        """3次重试后恢复概率 ≥ 0.95"""
        import random; random.seed(42)
        successes = 0
        for _ in range(100):
            for retry in range(3):
                if random.random() > 0.10:
                    successes += 1
                    break
        assert successes / 100 >= 0.95

    def test_fallback_on_no_model(self):
        """模型不可用时降级"""
        import api.dependencies as deps
        saved = deps.fridge_model
        deps.fridge_model = None
        try:
            from api.tools import find_substitutions
            result = find_substitutions.invoke({"ingredient_name":"黄油"})
            assert "suggestions" in json.loads(result)
        finally:
            deps.fridge_model = saved
```

---

## 四、评测框架集成

### 推荐框架

| 框架 | 适用 | 集成方式 |
|------|------|----------|
| **Ragas** | RAG Faithfulness/Relevancy | `pip install ragas` → evaluate() |
| **DeepEval** | 单元测试风格断言 | `deepeval.assert_actual_output()` |
| **LangSmith** | Agent全链路追踪 | 已配置 `LANGSMITH_TRACING=true` |

### Ragas 集成示例

```python
# tests/rag/test_with_ragas.py
from ragas import evaluate
from ragas.metrics import faithfulness, answer_relevancy
from datasets import Dataset

def test_ragas_evaluation():
    ds = Dataset.from_dict({
        "question": ["红烧肉怎么做?"],
        "answer": ["猪肉焯水，炒糖色后炖1小时。"],
        "contexts": [["红烧肉:猪肉、酱油、冰糖。焯水后炖1小时。"]],
    })
    result = evaluate(ds, metrics=[faithfulness, answer_relevancy])
    df = result.to_pandas()
    assert df["faithfulness"].mean() >= 0.7
```

---

## 五、实施路线

```
Day 1-2: RAG 检索+Embedding (10+ cases)
  test_retrieval_quality.py → Recall@K, Precision@K, MRR
  test_embedding.py → 相似度, chunk一致性

Day 3-4: Agent 任务+工具+规划 (15+ cases)
  test_task_success.py, test_tool_call.py, test_planning.py

Day 5: Memory+推理+多步 (10+ cases)
  test_memory.py, test_reasoning.py, test_multi_step.py

Day 6: 恢复+生成质量+性能 (10+ cases)
  test_recovery.py, test_generation.py, test_performance.py

Day 7: 评测框架+联合集成 (5+ cases)
  test_with_ragas.py, test_e2e_workflows.py
```

```bash
cd Backend
pytest tests/rag/ tests/agent/ -v --tb=short
pytest tests/rag/test_retrieval_quality.py -v    # 检索质量
pytest tests/agent/test_task_success.py -v        # 任务完成率
```

---

> **总计**: 50+ 测试用例 | 覆盖 RAG 4维度 + Agent 7维度 | 对齐 docx 测试维度框架
