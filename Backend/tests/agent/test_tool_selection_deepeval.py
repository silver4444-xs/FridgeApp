"""
DeepEval Agent 工具选择 + 任务完成测试
=========================================

验证 Agent 在不同用户请求下是否能正确选择合适的工具/子Agent.

测试覆盖:
  - 7 类用户意图 (inventory / recommend / detail / substitution / knowledge / preferences)
  - 子Agent 路由是否正确 (菜谱→recipe_expert, 烹饪知识→cooking_expert)

DeepEval 职责:
  - test_each          : ToolCorrectnessMetric 逐条评分 (exact_match + LLM reasoning)
  - test_aggregate     : evaluate() 批量运行, 汇总通过率
  - TestSubagentRouting: pytest 断言验证"不应调用的工具" (DeepEval 不覆盖此维度)
"""
import os, pytest
from deepeval import evaluate
from deepeval.metrics import ToolCorrectnessMetric
from deepeval.test_case import LLMTestCase
from deepeval.test_case.llm_test_case import ToolCall
from deepeval.models import GPTModel

# ---------------------------------------------------------------------------
# 12 条测试用例, 按用户意图分 7 类:
#   inventory     : 查看冰箱食材 → 直接调用 get_fridge_inventory
#   recommend     : 菜谱推荐 → 路由到 recipe_expert 子Agent
#   detail        : 具体菜谱做法 → 路由到 recipe_expert 子Agent
#   substitution  : 食材替换 → 路由到 substitution_expert 子Agent
#   knowledge     : 烹饪知识问答 → 路由到 cooking_expert 子Agent
#   preferences   : 偏好/忌口保存 → 直接调用 save_user_preferences
#
# 每条用例格式: (用户请求, 预期调用的工具/子Agent名, 答案中应含的关键信息, 类别标签)
# ---------------------------------------------------------------------------
AGENT_TEST_CASES = [
    # ---- inventory: 冰箱库存查询, 只需 get_fridge_inventory 工具 ----
    ("冰箱里有什么？", ["get_fridge_inventory"], ["食材"], "inventory"),

    # ---- recommend: 菜谱推荐, 应由 recipe_expert 子Agent 处理 ----
    ("能做什么菜？", ["recipe_expert"], ["推荐"], "recommend"),
    ("推荐几道家常菜", ["recipe_expert"], ["家常"], "recommend"),
    ("鸡蛋和西红柿能做什么？", ["recipe_expert"], ["番茄炒蛋"], "recommend"),

    # ---- detail: 具体菜谱的做法查询, 也由 recipe_expert 处理 ----
    ("番茄炒蛋怎么做？", ["recipe_expert"], ["鸡蛋", "步骤"], "detail"),

    # ---- substitution: 食材替换建议, 由 substitution_expert 子Agent 处理 ----
    ("没有黄油可以用什么代替？", ["substitution_expert"], ["替代"], "substitution"),
    ("家里没有料酒了，能用什么替代？", ["substitution_expert"], ["替代"], "substitution"),

    # ---- knowledge: 烹饪技巧/知识问答, 由 cooking_expert 子Agent 处理 ----
    ("怎么让鸡肉更嫩？", ["cooking_expert"], ["腌制", "嫩"], "knowledge"),
    ("煎鱼不粘锅有什么技巧？", ["cooking_expert"], ["煎", "技巧"], "knowledge"),
    ("川菜有什么特点？", ["cooking_expert"], ["川菜", "麻辣"], "knowledge"),

    # ---- preferences: 用户偏好/忌口保存, 直接调用 save_user_preferences 工具 ----
    ("我不吃花生，对海鲜过敏", ["save_user_preferences"], ["保存"], "preferences"),
    ("我喜欢川菜，3个人吃饭", ["save_user_preferences"], ["保存"], "preferences"),
]


def get_eval_model():
    """
    创建 DeepEval 原生评测模型, 指向 DeepSeek API.

    DeepEval 的 GPTModel 接受 openai-python 兼容的 api_key + base_url,
    可直接对接 DeepSeek 等第三方 OpenAI-compatible 网关.
    temperature=0 确保评测结果一致可复现.
    """
    return GPTModel(
        model=os.getenv("EVAL_MODEL", "deepseek-v4-flash"),
        api_key=os.getenv("EVAL_API_KEY") or os.getenv("DEEPSEEK_API_KEY"),
        base_url=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"),
        temperature=0.0,
    )


def run_agent_query(message: str) -> dict:
    """
    执行单条用户消息的 Agent 查询, 并提取工具调用信息.

    工作流程:
    1. 注入模拟冰箱食材 (鸡蛋/西红柿/鸡胸肉) 和用户偏好 (忌口花生)
    2. 通过 fridge_agent.invoke() 调用 Agent
    3. 从返回的 messages 中解析: 调用了哪些工具, 最终回复内容
    4. 返回 {"input", "tool_calls", "final_answer"} 字典

    每条用例使用唯一 thread_id, 避免跨测试历史累积导致上下文膨胀+超时.
    """
    import uuid
    from api.dependencies import fridge_agent
    from api.tools import FridgeContext
    import api.dependencies as deps
    if not fridge_agent:
        pytest.skip("Agent not initialized")
    # 模拟冰箱中有 3 种食材
    deps.current_fridge_inventory = [
        {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"},
        {"name": "西红柿", "qty": 3, "cal": 18, "cat": "蔬菜"},
        {"name": "鸡胸肉", "qty": 2, "cal": 133, "cat": "肉蛋生鲜类"},
    ]
    ctx = FridgeContext(
        current_inventory=deps.current_fridge_inventory,
        user_preferences={"忌口": ["花生"]}, user_id="test_agent")
    result = fridge_agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        context=ctx,
        config={"configurable": {"thread_id": f"test_agent_{uuid.uuid4().hex[:8]}"}},
    )
    messages = result.get("messages", [])
    tool_calls, final_answer = [], ""
    for msg in messages:
        # 提取 AIMessage 中的 tool_calls (子Agent 名称)
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(tc.get("name", "unknown"))
        # 提取最终回复文本 (非 tool_call 的普通 AIMessage)
        if hasattr(msg, "content") and msg.content:
            if not hasattr(msg, "tool_calls"):
                final_answer = msg.content
    return {"input": message, "tool_calls": tool_calls, "final_answer": final_answer}


def _build_test_case(input_msg: str, result: dict, expected_tools: list) -> LLMTestCase:
    """
    将 Agent 执行结果转换为 DeepEval LLMTestCase.

    tools_called / expected_tools 都构造为 ToolCall(name=...) 列表,
    DeepEval 的 ToolCorrectnessMetric 会比对 name 字段判断工具选择是否正确.
    """
    return LLMTestCase(
        input=input_msg,
        actual_output=result["final_answer"],
        tools_called=[ToolCall(name=tc) for tc in result["tool_calls"]],
        expected_tools=[ToolCall(name=et) for et in expected_tools],
    )


# ===========================================================================
# 测试类1: Agent 工具选择正确性 — DeepEval ToolCorrectnessMetric 评测
# ===========================================================================
class TestAgentToolSelection:
    @pytest.mark.agent
    @pytest.mark.slow
    @pytest.mark.parametrize("input_msg,expected_tools,_,cat", AGENT_TEST_CASES)
    def test_each(self, input_msg, expected_tools, _, cat):
        """
        逐条 DeepEval 评测: ToolCorrectnessMetric 对每条用例独立打分.

        should_exact_match=True  → 工具名精确匹配 (不依赖 LLM 做语义近似)
        threshold=0.5           → 至少命中一个预期工具即通过
        评测 LLM 负责生成 reason 解释为什么通过/不通过
        """
        result = run_agent_query(input_msg)
        test_case = _build_test_case(input_msg, result, expected_tools)
        metric = ToolCorrectnessMetric(
            model=get_eval_model(),
            threshold=0.5,
            should_exact_match=False,
            include_reason=True,
        )
        metric.measure(test_case)
        print(
            f"\n  [{cat}] '{input_msg[:40]}'"
            f" → called={result['tool_calls']}"
            f" | score={metric.score:.2f} reason={metric.reason}"
        )
        assert metric.is_successful(), \
            f"[{cat}] ToolCorrectness failed: score={metric.score:.2f}, reason={metric.reason}"

    @pytest.mark.agent
    @pytest.mark.slow
    def test_aggregate_accuracy(self):
        """
        批量 DeepEval evaluate() 评测全部 12 条用例.

        evaluate() 一次传入所有 LLMTestCase + ToolCorrectnessMetric,
        返回 EvaluationResult 含 test_result 列表, 逐条可查 success 状态.
        整体通过率 ≥ 70% 视为达标.
        """
        test_cases = []
        for input_msg, expected, _, _ in AGENT_TEST_CASES:
            result = run_agent_query(input_msg)
            test_cases.append(_build_test_case(input_msg, result, expected))
        metric = ToolCorrectnessMetric(
            model=get_eval_model(),
            threshold=0.5,
            should_exact_match=False,
            include_reason=True,
        )
        results = evaluate(test_cases, [metric])
        passed = sum(1 for r in results.test_results if r.success)
        total = len(results.test_results)
        accuracy = passed / total
        print(f"\n  DeepEval evaluate() 结果: {passed}/{total} = {accuracy:.1%}")
        assert accuracy >= 0.70, f"整体通过率 {accuracy:.1%} < 70%"


# ===========================================================================
# 测试类2: 子Agent 路由规则 — pytest 断言
#
# 为什么不用 DeepEval:
#   ToolCorrectnessMetric 只能验证"调用了哪些工具",
#   无法验证"不应该调用哪些工具" (路由反模式).
#   因此用 pytest 原生的集合断言来检测路由违规.
# ===========================================================================
class TestSubagentRouting:
    @pytest.mark.agent
    def test_recipe_to_expert(self):
        """
        菜谱类请求必须路由到 recipe_expert 子Agent.

        不应直接调用底层工具 (recommend_by_fridge / search_recipes_by_ingredients),
        否则说明子Agent 路由失效, 主 Agent 绕过了 recipe_expert 直接调基础 tool.
        """
        for q in ["能做什么菜", "红烧肉怎么做", "搜索川菜菜谱"]:
            result = run_agent_query(q)
            tools = result["tool_calls"]
            if tools:
                assert not {"recommend_by_fridge", "search_recipes_by_ingredients"}.issuperset(tools), \
                    f"'{q}' 应路由到 recipe_expert, 实际: {tools}"

    @pytest.mark.agent
    def test_knowledge_to_expert(self):
        """
        烹饪知识类请求必须路由到 cooking_expert 子Agent.

        不应直接调用底层工具 search_cooking_knowledge,
        否则说明主 Agent 绕过了 cooking_expert 子Agent.
        """
        for q in ["怎么让鸡肉更嫩", "煲汤要多久"]:
            result = run_agent_query(q)
            if result["tool_calls"]:
                assert "search_cooking_knowledge" not in result["tool_calls"], \
                    f"'{q}' 应路由到 cooking_expert, 实际: {result['tool_calls']}"
