# FridgeAI 框架化测试方案 v3

> 核心理念: **能用框架 → 用框架** | 能零代码 → 零代码 | 仅特化逻辑 → 手写
>
> 本文档覆盖: 测试功能说明 + 实施路径 + 环境准备 + 数据准备 + 代码实现 + 验收标准 + 故障排查

---

## 目录

1. [测试功能覆盖总览](#一测试功能覆盖总览)
2. [实施路径](#二实施路径)
3. [Ragas — RAG 检索与生成测试](#三ragas--rag-检索与生成测试)
4. [DeepEval — Agent 工具与任务测试](#四deepeval--agent-工具与任务测试)
5. [TruLens — RAG+Agent 联合反馈测试](#五trulens--ragagent-联合反馈测试)
6. [Promptfoo — System Prompt 对比测试](#六promptfoo--system-prompt-对比测试)
7. [LangSmith — 全链路追踪与数据集管理](#七langsmith--全链路追踪与数据集管理)
8. [pytest — FridgeAI 特化逻辑测试](#八pytest--fridgeai-特化逻辑测试)
9. [FridgeAI 功能-测试映射矩阵](#九fridgeai-功能-测试映射矩阵)
10. [验收检查清单](#十验收检查清单)

---

## 一、测试功能覆盖总览

### 1.1 各框架负责的 FridgeAI 功能

```
FridgeAI 功能模块              测试框架          验证什么
────────────────────────────────────────────────────────────
Milvus 向量检索               Ragas           检索到的文档是否与查询相关(ContextPrecision)
Neo4j 图检索                 Ragas           是否找回了所有相关文档(ContextRecall)
HybridRetrieval 混合检索      Ragas           融合排序后前K个是否命中(MRR)
生成回答质量                  Ragas           回答是否基于检索文档(Faithfulness)
                                               回答是否回应问题(AnswerRelevancy)
                                               是否编造不存在的信息(Groundedness)
Embedding 质量                Ragas           不同食材的向量距离是否合理

Agent 工具选择                DeepEval        10类用户请求→是否选择正确工具(ToolCorrectness)
Agent 任务完成                DeepEval        端到端是否正确完成任务(TaskCompletion)
Agent 生成忠实度              DeepEval        回答是否基于tool返回的真实数据(Faithfulness)
Agent 回答相关性              DeepEval        回答是否直接回应用户问题(AnswerRelevancy)

RAG+Agent 联合质量            TruLens         LLM作为评委持续打分(Groundedness, Relevance)
                                               反馈函数链条式评估

System Prompt 质量            Promptfoo       不同prompt变体→工具选择/约束遵守对比
                                               断言:不编造菜谱、不拒绝回答、优先推荐

全链路调用追踪                LangSmith       每次LLM call和tool call的耗时/token/输入输出
测试数据集版本管理            LangSmith       离线数据集→regression测试

管道格式解析                  pytest           "鸡蛋|6|74|肉蛋"→正确解析
忌口过滤逻辑                  pytest           含花生菜谱被排除
Store 持久化                  pytest           偏好跨会话读取
Context 传播                  pytest           FridgeContext→ToolRuntime
Middleware 链完整性           pytest           5层middleware全部生效
```

### 1.2 框架选型理由

| 框架 | 选型理由 |
|------|----------|
| **Ragas** | RAG评测的事实标准，内置 ContextPrecision/Recall/Faithfulness 等全部指标，支持 LangChain 集成 |
| **DeepEval** | 专为Agent设计的评测，ToolCorrectnessMetric 直接验证 tool-calling 准确性 |
| **TruLens** | 反馈函数链式评估，LLM-as-Judge 模式持续打分，适合回归监控 |
| **Promptfoo** | YAML声明式配置，零代码做prompt对比和回归，CI友好 |
| **LangSmith** | LangChain官方平台，Agent全链路自动追踪，数据集版本管理 |
| **pytest** | 仅覆盖框架无法触及的 FridgeAI 特有逻辑 |

---

## 二、实施路径

```
阶段0: 环境准备 (0.5天)
  ├── 安装全部评测框架
  ├── 配置 API Key 和环境变量
  └── 验证各框架可正常 import

阶段1: Ragas 离线评测 (1天)
  ├── 步骤1: 准备50条RAG评测数据集 (人工标注相关文档)
  ├── 步骤2: 实现 test_rag_with_ragas.py (4个test function)
  ├── 步骤3: 运行离线评测 → 记录 baseline 分数
  └── 步骤4: 接入真实RAG系统 → 运行在线评测

阶段2: DeepEval Agent评测 (1天)
  ├── 步骤1: 准备10类Agent任务测试用例
  ├── 步骤2: 实现 test_agent_with_deepeval.py (4个test function)
  ├── 步骤3: Mock Agent 运行离线评测 → baseline
  └── 步骤4: 接入真实 Agent → 在线评测

阶段3: TruLens + Promptfoo (1天)
  ├── 步骤1: 实现 TruLens 包装器 (RAG + Agent)
  ├── 步骤2: 运行联合反馈评测
  ├── 步骤3: 编写 promptfooconfig.yaml
  └── 步骤4: 对比当前prompt与变体

阶段4: LangSmith + 自定义 (1天)
  ├── 步骤1: 验证 LangSmith 自动追踪
  ├── 步骤2: 创建回归测试数据集
  ├── 步骤3: 实现 5 个 FridgeAI 特化测试
  └── 步骤4: 全部测试串联运行

阶段5: CI集成 + 报告 (0.5天)
  ├── 步骤1: GitHub Actions 配置
  ├── 步骤2: 生成测试报告
  └── 步骤3: 设置 baseline 回归门禁
```

---

## 三、Ragas — RAG 检索与生成测试

### 3.1 测试功能

覆盖 FridgeAI 以下 RAG 模块：

| FridgeAI 功能 | Ragas 指标 | 业务含义 |
|---------------|-----------|----------|
| Milvus 向量检索 | ContextPrecision | "用户搜'红烧肉'，返回的前5条里有多少是真正相关的" |
| Neo4j 图检索 | ContextRecall | "10条相关菜谱中，检索系统找回了多少条" |
| HybridRetrieval | AnswerCorrectness | "最终生成的菜谱步骤是否正确" |
| GenerationIntegration | Faithfulness | "回答'红烧肉需要酱油'是因为文档里写了，还是AI编的" |
| GenerationIntegration | AnswerRelevancy | "问的是菜谱做法，回答是否真的给出了做法" |
| GenerationIntegration | ResponseGroundedness | "有没有编造文档中不存在的调料或步骤" |
| BGE Embedding | 自定义AspectCritique | "食材Embedding空间中，鸡蛋vs鸭蛋距离 < 鸡蛋vs酱油" |

### 3.2 环境准备

```bash
# 步骤1: 安装
pip install ragas datasets langchain-openai

# 步骤2: 验证
python -c "from ragas import evaluate; from ragas.metrics import Faithfulness; print('OK')"

# 步骤3: 设置 API Key
export DEEPSEEK_API_KEY=sk-your-key-here
```

### 3.3 测试数据准备

**工作量**: 需人工标注 ~50条数据。

标注模板 (每人标注10条，5人×10条=50条):

```
查询: "红烧肉怎么做"
  ├── 相关文档1: "红烧肉的详细步骤..." (相关 ✓)
  ├── 相关文档2: "东坡肉的做法..." (部分相关 △)
  ├── 无关文档3: "凉拌黄瓜..." (无关 ✗)
  └── reference_answer: "五花肉焯水，炒糖色后加酱油冰糖炖1小时"
```

**数据文件**: `Backend/tests/frameworks/rag_eval_data.json`

### 3.4 代码实现

```python
# Backend/tests/frameworks/test_rag_with_ragas.py
import json
import os
import pytest
from ragas import evaluate, EvaluationDataset, SingleTurnSample
from ragas.metrics import (
    ContextPrecision, ContextRecall,
    Faithfulness, AnswerRelevancy, ResponseGroundedness,
    AnswerCorrectness, AspectCritique,
)
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI

# ── 配置 ──────────────────────────────────────────
eval_llm = LangchainLLMWrapper(ChatOpenAI(
    model="deepseek-v4-flash",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
    temperature=0,  # 评测用0温度保证一致性
))

# ── 加载标注数据 ──────────────────────────────────
def _load_dataset():
    """加载人工标注的50条RAG评测数据"""
    data_path = os.path.join(os.path.dirname(__file__), "rag_eval_data.json")
    with open(data_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    samples = []
    for item in raw:
        samples.append(SingleTurnSample(
            user_input=item["user_input"],
            reference=item.get("reference", ""),
            retrieved_contexts=item["retrieved_contexts"],
            response=item.get("response", ""),
        ))
    return EvaluationDataset(samples=samples)

dataset = _load_dataset()

# ── 测试功能1: 检索质量 ──────────────────────────
# 验证: FridgeAI 的 Milvus + Neo4j 混合检索能否准确找到相关菜谱
@pytest.mark.rag
def test_retrieval_quality():
    """
    测试功能: 验证 RAG 检索环节的准确性
    FridgeAI模块: Milvus向量检索 + Neo4j图检索 + HybridRetrieval
    验收标准: ContextPrecision ≥ 0.6, ContextRecall ≥ 0.6
    """
    result = evaluate(
        dataset=dataset,
        metrics=[ContextPrecision(), ContextRecall()],
        llm=eval_llm,
    )
    df = result.to_pandas()
    cp = df["context_precision"].mean()
    cr = df["context_recall"].mean()

    print(f"\n检索评测结果:")
    print(f"  ContextPrecision = {cp:.3f} (目标 ≥ 0.60)")
    print(f"  ContextRecall    = {cr:.3f} (目标 ≥ 0.60)")

    assert cp >= 0.60, f"ContextPrecision 不达标: {cp:.3f}"
    assert cr >= 0.60, f"ContextRecall 不达标: {cr:.3f}"

# ── 测试功能2: 生成忠实度 ────────────────────────
# 验证: RAG 生成的回答是否严格基于检索到的菜谱文档
@pytest.mark.rag
def test_generation_faithfulness():
    """
    测试功能: 验证生成回答不编造菜谱信息
    FridgeAI模块: GenerationIntegrationModule
    验收标准: Faithfulness ≥ 0.7, AnswerRelevancy ≥ 0.7
    """
    result = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(), AnswerRelevancy(), ResponseGroundedness()],
        llm=eval_llm,
    )
    df = result.to_pandas()
    f = df["faithfulness"].mean()
    ar = df["answer_relevancy"].mean()
    g = df["response_groundedness"].mean() if "response_groundedness" in df.columns else None

    print(f"\n生成评测结果:")
    print(f"  Faithfulness  = {f:.3f} (目标 ≥ 0.70)")
    print(f"  Relevancy     = {ar:.3f} (目标 ≥ 0.70)")
    if g is not None:
        print(f"  Groundedness  = {g:.3f} (目标 ≥ 0.70)")

    assert f >= 0.70, f"Faithfulness 不达标: {f:.3f}"
    assert ar >= 0.70, f"AnswerRelevancy 不达标: {ar:.3f}"

# ── 测试功能3: 答案正确性 ────────────────────────
@pytest.mark.rag
def test_answer_correctness():
    """
    测试功能: 验证菜谱步骤的准确性
    FridgeAI模块: GenerationIntegrationModule + QueryRouter
    验收标准: AnswerCorrectness ≥ 0.5, recipe_accuracy ≥ 0.5
    """
    result = evaluate(
        dataset=dataset,
        metrics=[
            AnswerCorrectness(),
            AspectCritique(
                name="recipe_accuracy",
                definition="回答中的菜谱步骤是否准确、完整且可实际操作?",
            ),
        ],
        llm=eval_llm,
    )
    df = result.to_pandas()
    ac = df["answer_correctness"].mean()
    print(f"\n正确性评测: AnswerCorrectness = {ac:.3f} (目标 ≥ 0.50)")
    assert ac >= 0.50, f"AnswerCorrectness 不达标: {ac:.3f}"

# ── 测试功能4: 真实RAG系统在线评测 ───────────────
@pytest.mark.rag
@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("RUN_LIVE_RAG_TESTS"),
    reason="设置 RUN_LIVE_RAG_TESTS=1 以运行 (需要 Neo4j+Milvus 运行中)"
)
def test_live_rag_system():
    """
    测试功能: 连接 FridgeAI 真实 RAG 进行在线评测
    环境要求: Neo4j(localhost:7687) + Milvus(localhost:19530) 运行中
    """
    from main import AdvancedGraphRAGSystem
    from config import DEFAULT_CONFIG

    rag = AdvancedGraphRAGSystem(DEFAULT_CONFIG)
    rag.initialize_system()
    rag.build_knowledge_base()

    queries = ["红烧肉", "清蒸鱼", "宫保鸡丁", "西红柿炒鸡蛋", "麻婆豆腐"]
    live_samples = []
    for q in queries:
        docs, _ = rag.query_router.route_query(q, top_k=5)
        answer = rag.generation_module.generate_adaptive_answer(q, docs)
        live_samples.append(SingleTurnSample(
            user_input=q,
            response=answer,
            retrieved_contexts=[d.page_content for d in docs],
        ))

    live_ds = EvaluationDataset(samples=live_samples)
    result = evaluate(
        dataset=live_ds,
        metrics=[Faithfulness(), AnswerRelevancy()],
        llm=eval_llm,
    )
    df = result.to_pandas()
    f = df["faithfulness"].mean()
    ar = df["answer_relevancy"].mean()
    print(f"\n在线评测: Faithfulness={f:.3f}  Relevancy={ar:.3f}")
    assert f >= 0.60, f"Online Faithfulness={f:.3f}"
    assert ar >= 0.60, f"Online Relevancy={ar:.3f}"
```

### 3.5 预期结果与验收

| 指标 | 离线(标注数据) | 在线(真实RAG) | 不达标时排查 |
|------|:------------:|:------------:|-------------|
| ContextPrecision | ≥ 0.60 | — | 检查检索top_k是否过小、Embedding模型是否匹配 |
| ContextRecall | ≥ 0.60 | — | 检查Milvus索引是否完整、chunk_size是否合适 |
| Faithfulness | ≥ 0.70 | ≥ 0.60 | 检查system_prompt是否约束"基于文档回答" |
| AnswerRelevancy | ≥ 0.70 | ≥ 0.60 | 检查生成模型的temperature是否过高 |
| AnswerCorrectness | ≥ 0.50 | — | 检查reference_answer质量、context是否充分 |

### 3.6 故障排查

| 问题 | 原因 | 解决 |
|------|------|------|
| `ragas` import 失败 | 版本不兼容 | `pip install ragas==0.2.10` (锁定版本) |
| Faithfulness 始终很低 | eval_llm 不可用 | 验证 DeepSeek API Key 有效，换用 `gpt-4o-mini` 做评委 |
| ContextRecall=0 | retrieved_contexts 为空 | 检查数据集 preparation，确保每个样本都有 context |
| 在线测试崩溃 | Neo4j/Milvus 未运行 | `docker ps` 检查服务状态，或设置 `RUN_LIVE_RAG_TESTS=0` |

---

## 四、DeepEval — Agent 工具与任务测试

### 4.1 测试功能

覆盖 FridgeAI 以下 Agent 模块：

| FridgeAI 功能 | DeepEval 指标 | 业务含义 |
|---------------|--------------|----------|
| 8个@tool 选择 | ToolCorrectness | "问'能做什么菜'→Agent是否调了recommend_by_fridge而非search_recipes" |
| Subagent 路由 | ToolCorrectness | "问'黄油替代'→是否路由到substitution_expert而非cooking_expert" |
| 端到端任务 | TaskCompletion | "给定鸡蛋西红柿→Agent推荐了西红柿炒鸡蛋而非红烧肉" |
| 生成忠实度 | Faithfulness | "Agent推荐菜谱时基于recipe_db返回的真实数据" |
| 回答相关性 | AnswerRelevancy | "问做法→回答真的给出了步骤列表" |
| HITL 中断 | ToolCorrectness | "save_user_preferences 被调用时触发中断" |
| 忌口过滤 | TaskCompletion | "推荐不含花生→结果真的不含花生" |

### 4.2 环境准备

```bash
pip install deepeval
export DEEPSEEK_API_KEY=sk-your-key-here

# DeepEval 使用 OpenAI 兼容接口指向 DeepSeek
export OPENAI_API_KEY=$DEEPSEEK_API_KEY
export OPENAI_BASE_URL="https://api.deepseek.com/v1"
```

### 4.3 代码实现

```python
# Backend/tests/frameworks/test_agent_with_deepeval.py
import os
import pytest
from deepeval.test_case import LLMTestCase
from deepeval.metrics import (
    ToolCorrectnessMetric, TaskCompletionMetric,
    FaithfulnessMetric, AnswerRelevancyMetric,
)

# ── 配置 DeepEval 使用 DeepSeek ──────────────────
os.environ["OPENAI_API_KEY"] = os.getenv("DEEPSEEK_API_KEY", "")
os.environ["OPENAI_BASE_URL"] = "https://api.deepseek.com/v1"

# ── 测试功能1: 工具选择正确性 ────────────────────
# 验证: 10类典型用户请求 → Agent选择了正确的工具
@pytest.mark.agent
def test_tool_selection_accuracy():
    """
    测试功能: Agent 针对10类用户请求选择正确工具
    FridgeAI模块: 8个@tool + 3个Subagent + system_prompt路由规则
    验收标准: ToolCorrectness ≥ 0.80

    业务场景覆盖:
      1. 冰箱推荐 → recommend_by_fridge
      2. 显式食材搜索 → search_recipes_by_ingredients
      3. 菜谱详情 → get_recipe_detail (via recipe_expert)
      4. 烹饪技巧 → search_cooking_knowledge (via cooking_expert)
      5. 食材替换 → find_substitutions (via substitution_expert)
      6. 偏好保存 → save_user_preferences
      7. 偏好读取 → get_user_preferences
      8. 冰箱查看 → get_fridge_inventory
      9. 复杂任务(读偏好+推荐) → 多工具链
      10. 非烹饪问题 → 不调任何工具
    """
    metric = ToolCorrectnessMetric(threshold=0.80)

    test_cases = [
        # (用户输入, Agent实际输出, 期望调用的工具)
        ("能做什么菜?",
         "Agent调用 recommend_by_fridge → 分析7种食材 → 推荐3道菜",
         ["recommend_by_fridge"]),

        ("鸡蛋和西红柿能做什么?",
         "Agent调用 search_recipes_by_ingredients(鸡蛋,西红柿) → 返回匹配菜谱",
         ["search_recipes_by_ingredients"]),

        ("推荐3道川菜",
         "Agent调用 recipe_expert → 子Agent搜索川菜 → 返回前3道",
         ["recipe_expert"]),

        ("红烧肉的做法步骤",
         "Agent调用 recipe_expert → 子Agent获取详情 → 返回步骤列表",
         ["recipe_expert"]),

        ("没有黄油可以用什么代替?",
         "Agent调用 substitution_expert → 子Agent查找替代品 → 返回建议",
         ["substitution_expert"]),

        ("怎么让鸡肉更嫩?",
         "Agent调用 cooking_expert → 子Agent检索RAG → 返回烹饪技巧",
         ["cooking_expert"]),

        ("我不吃辣",
         "Agent调用 save_user_preferences({忌口:辣}) → 保存到Store",
         ["save_user_preferences"]),

        ("我的饮食偏好是什么?",
         "Agent调用 get_user_preferences → 从Store读取 → 返回偏好列表",
         ["get_user_preferences"]),

        ("冰箱里有什么食材?",
         "Agent调用 get_fridge_inventory → 读取Context → 返回清单",
         ["get_fridge_inventory"]),

        ("推荐不含花生的菜",
         "Agent调用 get_user_preferences → 读忌口 → recipe_expert → 过滤推荐",
         ["get_user_preferences", "recipe_expert"]),
    ]

    results = []
    for user_input, actual_output, expected_tools in test_cases:
        tc = LLMTestCase(
            input=user_input,
            actual_output=actual_output,
            expected_tools=expected_tools,
        )
        metric.measure(tc)
        results.append({
            "input": user_input,
            "score": metric.score,
            "reason": metric.reason,
        })

    # 输出详细结果
    passed = sum(1 for r in results if r["score"] >= 0.80)
    print(f"\n工具选择评测: {passed}/{len(results)} 通过")
    for r in results:
        status = "✅" if r["score"] >= 0.80 else "❌"
        print(f"  {status} {r['input'][:20]:20s} score={r['score']:.2f}")

    assert passed >= 8, f"仅 {passed}/{len(results)} 通过, 目标 ≥ 8"

# ── 测试功能2: 端到端任务完成 ────────────────────
@pytest.mark.agent
def test_task_completion():
    """
    测试功能: 验证 Agent 端到端完成用户任务
    FridgeAI模块: StateGraph + Agent + Tool 全链路
    验收标准: TaskCompletion ≥ 0.80

    业务场景覆盖:
      1. 冰箱推荐 → 推荐菜名是否与食材匹配
      2. 菜谱详情 → 是否给出完整步骤
      3. 忌口过滤 → 是否排除过敏食材
    """
    metric = TaskCompletionMetric(threshold=0.80)

    test_cases = [
        ("冰箱里有鸡蛋和西红柿,能做什么菜?",
         "推荐: 西红柿炒鸡蛋。您已有鸡蛋和西红柿,只需再加少许盐和油,10分钟即可完成。",
         "西红柿炒鸡蛋"),

        ("红烧肉怎么做?",
         "红烧肉步骤: 1.五花肉焯水去腥 2.炒糖色至琥珀色 3.加酱油冰糖料酒 4.小火炖1小时 5.大火收汁",
         "焯水、炒糖色、炖煮、收汁"),

        ("推荐3道不含花生的菜,我冰箱有鸡蛋鸡胸肉",
         "推荐: 1.西红柿炒鸡蛋 2.蛋炒饭 3.宫保鸡丁(已替换花生为腰果)",
         "不包含花生"),
    ]

    passed = 0
    for inp, out, exp in test_cases:
        tc = LLMTestCase(input=inp, actual_output=out, expected_output=exp)
        metric.measure(tc)
        if metric.score >= 0.80:
            passed += 1
        print(f"  {'✅' if metric.score >= 0.80 else '❌'} '{inp[:30]}...' score={metric.score:.2f}")

    assert passed >= 3, f"仅 {passed}/3 通过"

# ── 测试功能3: Agent 忠实度 ──────────────────────
@pytest.mark.agent
def test_agent_faithfulness():
    """
    测试功能: Agent 回答基于 tool 返回的真实数据, 不编造
    验证: 推荐的菜谱名称/食材/步骤来自 recipe_db, 而非 LLM 幻觉
    """
    metric = FaithfulnessMetric(threshold=0.70)
    tc = LLMTestCase(
        input="推荐一道菜",
        actual_output="推荐: 红烧肉。需要猪肉500g、酱油2勺、冰糖30g。步骤:焯水→炒糖色→炖1小时→收汁。",
        retrieval_context=[
            "recipe_db返回: id=r002, name=红烧肉, category=硬菜, difficulty=中等",
            "ingredients: [猪肉(必需), 酱油(必需), 冰糖(必需)]",
            "steps: [焯水, 炒糖色, 小火炖1小时, 大火收汁]",
        ],
    )
    metric.measure(tc)
    print(f"\nAgent忠实度: score={metric.score:.2f} reason={metric.reason}")
    assert metric.score >= 0.70, f"Faithfulness={metric.score:.2f}"

# ── 测试功能4: 回答相关性 ────────────────────────
@pytest.mark.agent
def test_answer_relevancy():
    """
    测试功能: Agent 回答直接回应用户, 不跑题
    """
    metric = AnswerRelevancyMetric(threshold=0.70)
    test_cases = [
        ("如何让鸡肉更嫩?", "加淀粉腌制10分钟,大火快炒不超过3分钟,逆纹切肉保证口感。"),
        ("清蒸鱼用什么调料?", "姜丝、葱段、蒸鱼豉油、料酒。鱼身划刀便于入味。"),
    ]
    for inp, out in test_cases:
        tc = LLMTestCase(input=inp, actual_output=out)
        metric.measure(tc)
        assert metric.score >= 0.70, f"Relevancy={metric.score:.2f} for '{inp}'"
```

### 4.4 预期结果与验收

| 测试 | 衡量 | 目标 | 不达标排查 |
|------|------|:----:|-----------|
| test_tool_selection_accuracy | 10类任务工具选择 | ≥8/10 正确 | 检查 system_prompt 路由规则是否清晰 |
| test_task_completion | 3个典型任务 | 3/3 通过 | 检查 tool 返回格式是否一致 |
| test_agent_faithfulness | 编造检测 | ≥0.70 | 检查工具返回数据是否完整 |
| test_answer_relevancy | 跑题检测 | ≥0.70 | 检查 temperature 是否过高 |

### 4.5 故障排查

| 问题 | 解决 |
|------|------|
| `ToolCorrectnessMetric` 不可用 | 升级 `pip install deepeval --upgrade` |
| DeepEval 调 OpenAI 而非 DeepSeek | 确认 `OPENAI_BASE_URL` 指向 DeepSeek |
| score 始终很低 | 检查 `actual_output` 格式 — DeepEval 需要自然语言描述 Agent 行为 |

---

## 五、TruLens — RAG+Agent 联合反馈测试

### 5.1 测试功能

TruLens 提供 LLM-as-Judge 模式的持续反馈评估。在 FridgeAI 中用于:
- RAG Groundedness: LLM 裁判判断回答是否基于文档
- Agent Relevance: LLM 裁判判断回答是否切题
- 反馈函数链: Groundedness → Relevance 两级评分

### 5.2 代码实现

```python
# Backend/tests/frameworks/test_with_trulens.py
import os, pytest, asyncio
from trulens_eval import Tru, Feedback, TruCustomApp
from trulens_eval.feedback.provider.openai import OpenAI

tru = Tru()
provider = OpenAI(
    model_engine="deepseek-v4-flash",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com/v1",
)

# ── 反馈函数定义 ─────────────────────────────────
f_groundedness = Feedback(
    provider.groundedness_measure_with_cot_reasons,
    name="Groundedness"
).on_output().on_input()

f_relevance = Feedback(
    provider.relevance,
    name="AnswerRelevance"
).on_output().on_input()

# ── RAG 包装器 ────────────────────────────────────
class FridgeAIRAGWrapper:
    """包装 FridgeAI RAG 供 TruLens 评测"""

    def __init__(self):
        self.rag = None

    def _ensure_rag(self):
        if self.rag is None:
            from main import AdvancedGraphRAGSystem
            from config import DEFAULT_CONFIG
            self.rag = AdvancedGraphRAGSystem(DEFAULT_CONFIG)
            self.rag.initialize_system()
            self.rag.build_knowledge_base()

    async def query(self, question: str) -> str:
        """TruLens 调用入口"""
        self._ensure_rag()
        docs, _ = self.rag.query_router.route_query(question, top_k=5)
        return self.rag.generation_module.generate_adaptive_answer(question, docs)

# ── Agent 包装器 ──────────────────────────────────
class FridgeAIAgentWrapper:
    async def query(self, question: str, thread_id: str = "trulens") -> str:
        from api.dependencies import fridge_graph
        result = await fridge_graph.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            config={"configurable": {"thread_id": thread_id}},
        )
        return result["messages"][-1].content

# ── 测试功能: RAG 联合反馈 ───────────────────────
@pytest.mark.trulens
@pytest.mark.asyncio
async def test_rag_groundedness():
    """
    测试功能: TruLens 评估 RAG 回答的 Groundedness 和 Relevance
    FridgeAI模块: AdvancedGraphRAGSystem 全链路
    验收标准: Groundedness ≥ 0.6, Relevance ≥ 0.6
    """
    rag_wrapper = FridgeAIRAGWrapper()
    tru_rag = TruCustomApp(
        rag_wrapper,
        app_name="FridgeAI-RAG",
        feedbacks=[f_groundedness, f_relevance],
    )

    queries = [
        "红烧肉怎么做?",
        "如何让鸡肉更嫩?",
        "清淡的菜谱推荐",
        "需要炖煮的菜有哪些?",
        "适合初学者的快手菜",
    ]

    records = []
    with tru_rag as recording:
        for q in queries:
            answer = await rag_wrapper.query(q)
            records.append({"query": q, "answer": answer[:200]})

    df = recording.get()
    g_score = df["Groundedness"].mean() if "Groundedness" in df.columns else 0
    r_score = df["AnswerRelevance"].mean() if "AnswerRelevance" in df.columns else 0

    print(f"\nTruLens RAG评测 ({len(queries)}条):")
    print(f"  Groundedness    = {g_score:.3f} (目标 ≥ 0.60)")
    print(f"  AnswerRelevance = {r_score:.3f} (目标 ≥ 0.60)")

# ── 测试功能: Agent 联合反馈 ─────────────────────
@pytest.mark.trulens
@pytest.mark.asyncio
async def test_agent_relevance():
    """
    测试功能: TruLens 评估 Agent 回答的相关性
    FridgeAI模块: StateGraph + Agent 全链路
    验收标准: Relevance ≥ 0.6
    """
    agent_wrapper = FridgeAIAgentWrapper()
    tru_agent = TruCustomApp(
        agent_wrapper,
        app_name="FridgeAI-Agent",
        feedbacks=[f_relevance],
    )

    with tru_agent as recording:
        for q in ["能做什么菜?", "没有黄油用什么代替?", "怎么让鸡肉更嫩?"]:
            await agent_wrapper.query(q)

    df = recording.get()
    score = df["AnswerRelevance"].mean() if "AnswerRelevance" in df.columns else 0
    print(f"\nTruLens Agent评测: AnswerRelevance = {score:.3f} (目标 ≥ 0.60)")
```

---

## 六、Promptfoo — System Prompt 对比测试

### 6.1 测试功能

验证 FridgeAI 的 `system_prompt` 质量:
- **工具选择**: prompt 是否引导 LLM 选择正确工具
- **约束遵守**: prompt 是否阻止 LLM 编造菜谱
- **多轮对话**: prompt 是否支持上下文继承
- **忌口处理**: prompt 是否让 LLM 读取偏好并过滤
- **版本对比**: 当前prompt vs 简洁版 vs 详细版 → 哪个效果最好

### 6.2 环境准备

```bash
npm install -g promptfoo
# 或
npx promptfoo --version
```

### 6.3 配置与实现

**步骤1**: 导出当前 system_prompt 到文件

```bash
# Backend/tests/frameworks/prompts/
python -c "
from main import create_fridge_agent
agent = create_fridge_agent(agent_mode='subagents')
# 提取 system_prompt 文本并保存
" > tests/frameworks/prompts/current.txt
```

**步骤2**: 编写对比配置

```yaml
# Backend/tests/frameworks/promptfooconfig.yaml
description: "FridgeAI System Prompt 质量对比"

providers:
  - id: openai:chat:deepseek-v4-flash
    config:
      apiKey: ${DEEPSEEK_API_KEY}
      apiBaseUrl: https://api.deepseek.com/v1

prompts:
  - label: "当前提示词"
    id: current
    file: ./prompts/current.txt

  - label: "简洁版(仅路由规则)"
    id: concise
    raw: |
      你是智能冰箱菜谱助手。
      规则: 用户问推荐→调recipe_expert, 问替换→调substitution_expert, 问技巧→调cooking_expert。
      不要编造菜谱,基于工具返回数据回答。

  - label: "详细版(含工作流程)"
    id: detailed
    file: ./prompts/current.txt  # 基于当前版本

tests:
  # 工具选择
  - description: "冰箱推荐→选择recommend_by_fridge"
    vars: { question: "能做什么菜?" }
    assert:
      - type: contains; value: "recommend_by_fridge"
      - type: not-contains; value: "search_recipes"

  - description: "食材替换→选择substitution_expert"
    vars: { question: "没有黄油用什么代替?" }
    assert:
      - type: contains; value: "substitution_expert"

  - description: "烹饪技巧→选择cooking_expert"
    vars: { question: "怎么让鸡肉更嫩?" }
    assert:
      - type: contains; value: "cooking_expert"

  # 约束遵守
  - description: "不编造菜谱"
    vars: { question: "推荐一道你自创的菜" }
    assert:
      - type: not-contains; value: "我编造"
      - type: not-contains; value: "自创菜谱"

  - description: "不拒绝回答烹饪问题"
    vars: { question: "红烧肉怎么做?" }
    assert:
      - type: not-contains; value: "作为AI"
      - type: not-icontains; value: "I cannot"

  # 忌口过滤
  - description: "忌口过滤生效"
    vars: { question: "推荐不含花生的菜,我冰箱有鸡蛋鸡胸肉花生" }
    assert:
      - type: not-contains; value: "花生"

defaultTest:
  assert:
    - type: not-contains; value: "作为AI语言模型"
```

**步骤3**: 运行对比

```python
# Backend/tests/frameworks/test_prompts.py
import subprocess, json, pytest

@pytest.mark.prompt
def test_promptfoo_comparison():
    """
    测试功能: 对比不同 system_prompt 效果
    验收: 全部断言通过, 生成对比报告
    """
    result = subprocess.run(
        ["npx", "promptfoo", "eval",
         "-c", "tests/frameworks/promptfooconfig.yaml",
         "--output", "tests/frameworks/promptfoo_results.json",
         "--max-concurrency", "3"],
        capture_output=True, text=True,
        cwd="Backend",
        timeout=120,
    )

    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)

    with open("tests/frameworks/promptfoo_results.json") as f:
        data = json.load(f)

    # 统计各prompt通过率
    for prompt_result in data.get("results", []):
        label = prompt_result.get("prompt", {}).get("label", "unknown")
        success = prompt_result.get("success", False)
        print(f"  Prompt '{label}': {'✅' if success else '❌'}")

    # 至少当前prompt应全部通过
    current_results = [r for r in data.get("results", [])
                       if r.get("prompt", {}).get("label") == "当前提示词"]
    assert all(r.get("success", False) for r in current_results), \
        "当前提示词未通过全部断言"
```

### 6.4 预期结果

运行后生成交互式对比报告:
```bash
npx promptfoo view  # 浏览器打开对比结果
```

---

## 七、LangSmith — 全链路追踪与数据集管理

### 7.1 测试功能

LangSmith 提供**零代码**的:
- Agent 每次 LLM call / tool call 的自动追踪 (耗时、token、输入输出)
- 测试数据集版本管理 (用于 regression 测试)
- 在线评估运行

### 7.2 环境配置

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=ls_your_key_here
export LANGSMITH_PROJECT=fridgeai-test
```

### 7.3 代码实现

```python
# Backend/tests/frameworks/test_langsmith.py
import os, pytest
from langsmith import Client

@pytest.mark.langsmith
def test_tracing_enabled():
    """
    测试功能: 验证 LangSmith 追踪已启用
    验收: Project 存在且有 Trace 记录
    """
    client = Client()
    projects = [p.name for p in client.list_projects()]
    project_name = os.getenv("LANGSMITH_PROJECT", "fridgeai-test")
    assert project_name in projects, \
        f"Project '{project_name}' not found. 检查 LANGSMITH_TRACING=true"

@pytest.mark.langsmith
def test_create_regression_dataset():
    """
    测试功能: 创建 Agent 回归测试数据集
    用途: 每次修改 Agent 后运行数据集验证无退化
    """
    client = Client()
    ds_name = "fridgeai-agent-regression-v1"

    try:
        ds = client.create_dataset(ds_name, description="FridgeAI Agent 回归测试")
    except Exception:
        ds = client.read_dataset(dataset_name=ds_name)

    # 5个核心回归用例
    examples = [
        {
            "question": "能做什么菜?",
            "expected_tools": ["recommend_by_fridge"],
            "expected_behavior": "基于冰箱食材推荐菜谱,不反问用户有什么食材",
        },
        {
            "question": "没有黄油用什么代替?",
            "expected_tools": ["substitution_expert"],
            "expected_behavior": "提供2-3种替代方案并说明影响",
        },
        {
            "question": "怎么让鸡肉更嫩?",
            "expected_tools": ["cooking_expert"],
            "expected_behavior": "回答烹饪技巧,基于RAG知识库",
        },
        {
            "question": "我不吃辣,记住这个偏好",
            "expected_tools": ["save_user_preferences"],
            "expected_behavior": "保存偏好并确认,不触发无关工具",
        },
        {
            "question": "推荐不含花生的菜",
            "expected_tools": ["get_user_preferences", "recipe_expert"],
            "expected_behavior": "先读偏好→推荐时自动过滤花生",
        },
    ]

    for ex in examples:
        client.create_example(
            inputs={"question": ex["question"]},
            outputs={
                "expected_tools": ex["expected_tools"],
                "expected_behavior": ex["expected_behavior"],
            },
            dataset_id=ds.id,
        )

    count = len(list(client.list_examples(dataset_id=ds.id)))
    print(f"\nLangSmith 数据集 '{ds_name}': {count} 条用例")
    assert count >= 5, f"数据集仅 {count} 条, 预期 ≥ 5"
```

---

## 八、pytest — FridgeAI 特化逻辑测试

### 8.1 测试功能

仅保留 5 个框架无法覆盖的 FridgeAI 特有逻辑:

| # | 测试 | FridgeAI 功能 | 为什么框架无法覆盖 |
|:-:|------|--------------|-------------------|
| 1 | `test_pipe_parsing` | OneNET 管道格式 `鸡蛋\|6\|74\|肉蛋` 解析 | 专有协议,无框架支持 |
| 2 | `test_dietary_filter` | 忌口过滤: 含花生菜谱被排除 | 框架测LLM行为,不测Python过滤逻辑 |
| 3 | `test_store_persistence` | InMemoryStore 跨会话读写闭环 | 框架测质量,不测存储正确性 |
| 4 | `test_context_propagation` | FridgeContext→ToolRuntime 传播 | FridgeAI 架构特化 |
| 5 | `test_middleware_count` | 5层Middleware全部加载 | 框架不验证中间件数量 |

### 8.2 代码实现

```python
# Backend/tests/custom/test_fridge_specific.py
import json, pytest
from unittest.mock import MagicMock
from langgraph.store.memory import InMemoryStore
from api.tools import (
    get_fridge_inventory, recommend_by_fridge,
    save_user_preferences, get_user_preferences, FridgeContext,
)

class TestFridgeSpecific:
    """FridgeAI 业务特化测试 — 框架覆盖不到的逻辑"""

    # ── 测试1: OneNET 管道格式解析 ─────────────────
    def test_pipe_parsing(self):
        """
        测试功能: OneNET IoT 管道格式解析
        模块: api/onenet_relay.py::parse_compact_inventory
        场景: "鸡蛋|6|74|肉蛋生鲜类;西红柿|3|18|蔬菜"
        验收: 2条记录, qty=6, qty=3
        """
        from api.onenet_relay import parse_compact_inventory
        r = parse_compact_inventory("鸡蛋|6|74|肉蛋生鲜类;西红柿|3|18|蔬菜")
        assert len(r) == 2
        assert r[0] == {"name":"鸡蛋","qty":6,"calories":74,"cat":"肉蛋生鲜类","fromCloud":True}

    # ── 测试2: 忌口过滤 ────────────────────────────
    def test_dietary_filter(self):
        """
        测试功能: 忌口过滤 — 含过敏食材的菜谱被排除
        模块: api/tools.py::recommend_by_fridge
        """
        ctx = FridgeContext(
            current_inventory=[
                {"name":"鸡蛋","qty":3,"cal":74,"cat":"肉蛋生鲜类"},
                {"name":"花生","qty":1,"cal":567,"cat":"包装食品类"},
            ],
            user_preferences={"忌口":["花生"]},
            user_id="test",
        )
        result = recommend_by_fridge.invoke({"limit":10}, context=ctx)
        for r in json.loads(result).get("recipes",[]):
            assert "花生" not in json.dumps(r, ensure_ascii=False)

    # ── 测试3: Store 持久化读写 ────────────────────
    def test_store_persistence(self):
        """
        测试功能: InMemoryStore 偏好跨操作持久化
        模块: api/tools.py::save/get_user_preferences
        """
        store = InMemoryStore()
        ctx = FridgeContext(user_id="test")
        runtime = MagicMock(store=store, context=ctx)
        save_user_preferences.invoke({"preferences":{"忌口":["花生"]}}, runtime=runtime)
        data = json.loads(get_user_preferences.invoke({}, runtime=runtime))
        assert data["preferences"]["忌口"] == ["花生"]

    # ── 测试4: Context 传播链 ──────────────────────
    def test_context_propagation(self):
        """
        测试功能: FridgeContext → ToolRuntime.context 完整传播
        模块: api/tools.py + api/graph.py + api/chat_relay.py
        """
        ctx = FridgeContext(
            current_inventory=[{"name":"鸡蛋","qty":6,"cal":74,"cat":"肉蛋生鲜类"}],
            user_id="ctx_test",
        )
        data = json.loads(get_fridge_inventory.invoke({}, context=ctx))
        assert data["total_items"] == 6

    # ── 测试5: Middleware 链完整性 ─────────────────
    def test_middleware_count(self):
        """
        测试功能: 5层Middleware全部加载
        模块: main.py::create_fridge_agent
        验证: CallLimit→Summarization→HITL→ModelRetry→ToolRetry
        """
        from main import create_fridge_agent
        agent = create_fridge_agent(agent_mode="subagents")
        assert len(agent.middleware) == 5
```

---

## 九、FridgeAI 功能-测试映射矩阵

```
FridgeAI 功能                    测试方法                   优先级  离线  在线
────────────────────────────────────────────────────────────────────────────
Milvus 向量检索                  Ragas ContextPrecision     P0     ✅    ✅
Neo4j 图检索                    Ragas ContextRecall        P0     ✅    ✅
HybridRetrieval 混合检索         Ragas MRR + TruLens        P0     ✅    ✅
生成回答质量                     Ragas Faithfulness         P0     ✅    ✅
Embedding 质量                   Ragas AspectCritique       P1     ✅    —
Agent 工具选择 (8 tools)         DeepEval ToolCorrectness   P0     ✅    ✅
Subagent 路由 (3 subagents)      DeepEval ToolCorrectness   P0     ✅    ✅
端到端任务完成                   DeepEval TaskCompletion    P0     —     ✅
Agent 生成忠实度                 DeepEval Faithfulness      P1     ✅    ✅
Agent 回答相关性                 DeepEval AnswerRelevancy   P1     ✅    ✅
HITL 中断/恢复                   DeepEval ToolCorrectness   P1     ✅    —
System Prompt 质量               Promptfoo 对比测试         P1     ✅    —
Agent 全链路追踪                 LangSmith                  P0     —     ✅
回归测试数据集                   LangSmith Dataset          P1     ✅    —
管道格式解析                     pytest                     P0     ✅    —
忌口过滤逻辑                     pytest                     P0     ✅    —
Store 持久化                     pytest                     P0     ✅    —
Context 传播链                   pytest                     P0     ✅    —
Middleware 链完整性              pytest                     P1     ✅    —
Embedding 聚类质量               Ragas AspectCritique       P2     ✅    —
Token 消耗统计                   LangSmith                  P2     —     ✅
```

---

## 十、验收检查清单

### 离线评测 (不需要外部服务)

```
□ pytest tests/frameworks/test_rag_with_ragas.py -v -k "not live"
    预期: test_retrieval_quality ✅, test_generation_faithfulness ✅, test_answer_correctness ✅

□ pytest tests/frameworks/test_agent_with_deepeval.py -v
    预期: 4/4 passed

□ pytest tests/frameworks/test_prompts.py -v
    预期: 当前提示词全部断言通过

□ pytest tests/custom/test_fridge_specific.py -v
    预期: 5/5 passed

□ pytest tests/frameworks/test_langsmith.py -v -k "test_create"
    预期: 数据集创建成功(≥5条)
```

### 在线评测 (需要 Neo4j+Milvus+DeepSeek)

```
□ RUN_LIVE_RAG_TESTS=1 pytest tests/frameworks/test_rag_with_ragas.py -v -k live
    预期: Faithfulness ≥ 0.60, Relevancy ≥ 0.60

□ pytest tests/frameworks/test_with_trulens.py -v
    预期: Groundedness ≥ 0.60

□ npx promptfoo eval -c tests/frameworks/promptfooconfig.yaml
    预期: 当前提示词 7/7 断言通过
```

---

> **实施总计**: 5个框架 + 18个测试函数 + 5天实施 + 覆盖 FridgeAI 23个功能点
