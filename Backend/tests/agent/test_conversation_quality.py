"""
Agent 多轮对话质量评测 — DeepEval 多轮指标。

测试范围:
  1. TestAgentConversationQuality : ConversationCompleteness + TurnRelevancy
  2. TestAgentFaithfulness       : TurnFaithfulness (防幻觉)
  3. TestAgentKnowledgeRetention : KnowledgeRetention (偏好记忆)

使用 DeepEval ConversationalTestCase + 多轮指标，评测 LLM 使用 DeepSeek。

DeepEval 4.0.7 API 适配说明:
  - Turn (不是 ConversationalTurn): role="user"|"assistant", content=str
  - ConversationCompletenessMetric 自动从 Turn 提取用户意图
  - 各指标 async_mode=False 避免 pytest 事件循环冲突
"""

import json
import os
import uuid
import pytest
from pathlib import Path
from typing import List, Dict


def load_conversation_scenarios() -> List[Dict]:
    """加载多轮对话场景数据集 (18 条)。"""
    path = Path(__file__).parent / "eval_data" / "conversation_scenarios.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_multi_turn_agent(turns: List[str], thread_id: str = None) -> Dict:
    """
    执行多轮 Agent 对话，返回每轮的工具调用和回复内容。

    Args:
        turns: 用户消息列表，每条对应一轮对话
        thread_id: 对话线程 ID (相同 ID 保持上下文)

    Returns:
        {"turns": [{"user": str, "assistant": str, "tool_calls": [str]}, ...],
         "final_answer": str}
    """
    import api.dependencies as deps
    from api.tools import FridgeContext

    if not deps.fridge_agent:
        pytest.skip("Agent not initialized")

    if thread_id is None:
        thread_id = f"conv_{uuid.uuid4().hex[:8]}"

    # 模拟冰箱食材
    deps.current_fridge_inventory = [
        {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"},
        {"name": "西红柿", "qty": 3, "cal": 18, "cat": "蔬菜"},
        {"name": "鸡胸肉", "qty": 2, "cal": 133, "cat": "肉蛋生鲜类"},
        {"name": "青椒", "qty": 4, "cal": 22, "cat": "蔬菜"},
    ]

    ctx = FridgeContext(
        current_inventory=deps.current_fridge_inventory,
        user_preferences={},
        user_id="test_agent_quality",
    )

    turn_results = []

    for i, user_msg in enumerate(turns):
        result = deps.fridge_agent.invoke(
            {"messages": [{"role": "user", "content": user_msg}]},
            context=ctx,
            config={"configurable": {"thread_id": thread_id}},
        )
        messages = result.get("messages", [])
        tool_calls = []
        assistant_text = ""

        for msg in messages:
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    tool_calls.append(tc.get("name", "unknown"))
            if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
                assistant_text = msg.content

        turn_results.append({
            "user": user_msg,
            "assistant": assistant_text,
            "tool_calls": tool_calls,
        })

    return {"turns": turn_results, "final_answer": turn_results[-1]["assistant"] if turn_results else ""}


def _make_conversational_turns(turn_results: List[Dict]) -> list:
    """
    将 run_multi_turn_agent 返回的 turn_results 转换为 DeepEval Turn 列表。

    DeepEval 4.0.7 的 Turn 使用 role/content 字段，按 user/assistant 交替排列。
    """
    from deepeval.test_case.conversational_test_case import Turn

    turns = []
    for tr in turn_results:
        turns.append(Turn(role="user", content=tr["user"]))
        turns.append(Turn(role="assistant", content=tr["assistant"]))
    return turns


def _build_eval_model():
    """构建 DeepEval 评测用 GPTModel (指向 DeepSeek API)。"""
    from deepeval.models import GPTModel

    api_key = os.getenv("EVAL_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        pytest.skip("Neither EVAL_API_KEY nor DEEPSEEK_API_KEY set")

    return GPTModel(
        model=os.getenv("EVAL_MODEL", "deepseek-v4-flash"),
        api_key=api_key,
        base_url=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"),
        temperature=0.0,
    )


class TestAgentConversationQuality:
    """多轮对话质量评测 — ConversationCompleteness + TurnRelevancy"""

    @pytest.mark.agent
    @pytest.mark.slow
    @pytest.mark.parametrize("scenario", [
        s for s in load_conversation_scenarios()
        if s["category"] in ("recommend_then_detail", "substitution_flow", "knowledge_followup")
    ])
    def test_conversation_completeness(self, scenario):
        """
        验证 Agent 是否满足对话中所有用户意图。

        对每条多轮场景执行完整对话，用 ConversationCompletenessMetric
        检查每轮用户意图是否被满足。阈值 >= 0.6。
        """
        from deepeval.metrics import ConversationCompletenessMetric
        from deepeval.test_case import ConversationalTestCase

        result = run_multi_turn_agent(scenario["turns"])

        eval_model = _build_eval_model()
        turns = _make_conversational_turns(result["turns"])

        test_case = ConversationalTestCase(
            turns=turns,
            scenario=scenario["scenario"],
        )

        metric = ConversationCompletenessMetric(
            model=eval_model, threshold=0.6, include_reason=True, async_mode=False)
        metric.measure(test_case)

        print(f"\n  [{scenario['category']}] '{scenario['scenario']}'")
        print(f"    Completeness: score={metric.score:.2f} reason={metric.reason}")
        print(f"    Tool calls: {[t['tool_calls'] for t in result['turns']]}")
        assert metric.is_successful(), \
            f"ConversationCompleteness failed: score={metric.score:.2f}"

    @pytest.mark.agent
    @pytest.mark.slow
    @pytest.mark.parametrize("scenario", load_conversation_scenarios())
    def test_turn_relevancy(self, scenario):
        """
        验证每轮 Agent 回复是否紧扣对话上下文。

        对每条多轮场景用 TurnRelevancyMetric 检查每轮回复相关性。
        阈值 >= 0.6。
        """
        from deepeval.metrics import TurnRelevancyMetric
        from deepeval.test_case import ConversationalTestCase

        result = run_multi_turn_agent(scenario["turns"])

        eval_model = _build_eval_model()
        turns = _make_conversational_turns(result["turns"])

        test_case = ConversationalTestCase(turns=turns, scenario=scenario["scenario"])

        metric = TurnRelevancyMetric(
            model=eval_model, threshold=0.6, include_reason=True, async_mode=False)
        metric.measure(test_case)

        print(f"\n  [{scenario['category']}] '{scenario['scenario']}'")
        print(f"    TurnRelevancy: score={metric.score:.2f} reason={metric.reason}")
        assert metric.is_successful(), \
            f"TurnRelevancy failed: score={metric.score:.2f}"


class TestAgentFaithfulness:
    """回复忠实度评测 — Agent 是否基于工具返回的真实数据回答，不编造菜谱"""

    @pytest.mark.agent
    @pytest.mark.slow
    def test_no_fabricated_recipes(self):
        """
        验证 Agent 在推荐+详情场景中不编造不存在的菜谱。

        使用 6 组固定问题序列执行多轮对话，TurnFaithfulnessMetric 评估。
        阈值 >= 0.7（防幻觉要求更严）。
        """
        from deepeval.metrics import TurnFaithfulnessMetric
        from deepeval.test_case import ConversationalTestCase

        eval_model = _build_eval_model()

        test_cases = [
            {"scenario": "番茄炒蛋真实性",
             "turns": ["鸡蛋和西红柿能做什么菜？", "番茄炒蛋的具体步骤是什么？"]},
            {"scenario": "宫保鸡丁真实性",
             "turns": ["鸡胸肉能做什么菜？", "宫保鸡丁怎么做？"]},
            {"scenario": "知识问答真实性",
             "turns": ["红烧肉需要什么调料？", "炒糖色具体怎么操作？"]},
            {"scenario": "替换方案真实性",
             "turns": ["没有料酒能用什么替代去腥？", "用姜片和花椒水怎么操作？"]},
            {"scenario": "查看食材真实性",
             "turns": ["冰箱里有什么？", "用这些食材能做什么？"]},
            {"scenario": "烹饪技巧真实性",
             "turns": ["煲汤应该注意什么？", "排骨汤一般煲多久？"]},
        ]

        all_passed = True
        for tc in test_cases:
            result = run_multi_turn_agent(tc["turns"])

            turns = _make_conversational_turns(result["turns"])

            conv_case = ConversationalTestCase(turns=turns, scenario=tc["scenario"])

            metric = TurnFaithfulnessMetric(
                model=eval_model, threshold=0.7, include_reason=True, async_mode=False)
            metric.measure(conv_case)

            print(f"\n  {tc['scenario']}: Faithfulness={metric.score:.2f} reason={metric.reason}")
            if not metric.is_successful():
                all_passed = False

        assert all_passed, "部分场景 TurnFaithfulness 未达标 (< 0.7)"


class TestAgentKnowledgeRetention:
    """跨轮偏好记忆评测 — 验证 save_user_preferences 链路"""

    @pytest.mark.agent
    @pytest.mark.slow
    @pytest.mark.parametrize("scenario", [
        s for s in load_conversation_scenarios()
        if s["category"] == "preference_memory"
    ])
    def test_knowledge_retention(self, scenario):
        """
        验证 Agent 在第 1 轮声明偏好后，第 2 轮推荐时是否记住。

        使用 KnowledgeRetentionMetric 检查关键信息是否跨轮保持。
        阈值 >= 0.6。
        """
        from deepeval.metrics import KnowledgeRetentionMetric
        from deepeval.test_case import ConversationalTestCase

        result = run_multi_turn_agent(scenario["turns"])

        eval_model = _build_eval_model()
        turns = _make_conversational_turns(result["turns"])

        test_case = ConversationalTestCase(turns=turns, scenario=scenario["scenario"])

        metric = KnowledgeRetentionMetric(
            model=eval_model, threshold=0.6, include_reason=True, async_mode=False)
        metric.measure(test_case)

        print(f"\n  {scenario['scenario']}")
        print(f"    Expected retained: {scenario.get('expected_knowledge_retained', [])}")
        print(f"    KnowledgeRetention: score={metric.score:.2f} reason={metric.reason}")
        assert metric.is_successful(), \
            f"KnowledgeRetention failed: score={metric.score:.2f}"
