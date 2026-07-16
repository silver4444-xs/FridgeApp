"""
LLM-as-Judge 评测 — 使用直接 LLM 调用评估回答质量

测试范围:
  - Groundedness (忠实度) : LLM 评估回答是否严格基于参考资料，未编造事实
  - Relevance (相关性)   : LLM 评估回答是否紧扣用户提问，无偏题

Note: 替代了 TruLens 1.x 的 Groundedness/Relevance (TruLens 2.x 已移除这些类)
"""
import os, json, pytest
from openai import OpenAI


def _eval_provider():
    """创建 LLM-as-Judge 所需的 OpenAI 客户端"""
    return OpenAI(
        api_key=os.getenv("EVAL_API_KEY", os.getenv("DEEPSEEK_API_KEY", "")),
        base_url=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"),
    )


def _judge(prompt: str) -> float:
    """调用 LLM 打分，返回 0.0–1.0 之间的分数"""
    client = _eval_provider()
    model = os.getenv("EVAL_MODEL", "deepseek-v4-flash")
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个评测助手。仅输出JSON对象，格式: {\"score\": <0到1之间的浮点数>, \"reason\": \"<一句话理由>\"}"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=256,
        response_format={"type": "json_object"},
    )
    result = json.loads(resp.choices[0].message.content)
    return float(result["score"])


class TestLLMJudge:
    """LLM-as-Judge 反馈评测 — 验证回答质量 (不涉及 Agent 调用)"""

    @pytest.mark.integration
    @pytest.mark.slow
    def test_groundedness(self):
        """检验回答是否忠实于参考资料: 用两份 (source, response) 对打分, 平均 >= 0.5 通过"""
        scores = []
        for source, response in [
            ("番茄炒蛋需要鸡蛋2个、番茄2个。步骤: 打蛋→炒蛋→炒番茄→混合调味。",
             "番茄炒蛋做法: 先打两个鸡蛋炒熟盛出, 再炒番茄至出汁, 最后混合调味即可。"),
            ("新鲜鸡蛋蛋壳粗糙有光泽，摇晃无声音，放入水中沉底。",
             "挑选鸡蛋要看蛋壳是否粗糙有光泽，摇晃检查是否无声，放入水中会沉底的就是新鲜鸡蛋。"),
        ]:
            prompt = f"""评估以下回答是否忠实于给定的参考资料（Groundedness）。

参考资料: {source}

回答: {response}

评估标准:
- 1.0: 回答完全基于参考资料，无任何编造
- 0.5: 回答大部分基于参考资料，有少量无关内容
- 0.0: 回答完全编造，与参考资料矛盾或无关

请打分。"""
            s = _judge(prompt)
            scores.append(s)
            print(f"  Groundedness: {s:.4f}")
        avg = sum(scores) / len(scores)
        print(f"\n  平均 Groundedness: {avg:.4f} (目标 >= 0.5)")
        assert avg >= 0.5

    @pytest.mark.integration
    @pytest.mark.slow
    def test_relevance(self):
        """检验回答是否紧扣提问: 用两份 (question, response) 对打分, 平均 >= 0.5 通过"""
        scores = []
        for question, response in [
            ("鸡蛋和番茄能做什么菜？",
             "鸡蛋和番茄最经典的搭配是番茄炒蛋，还可以做番茄蛋花汤、番茄鸡蛋面。"),
            ("煎鱼怎么不粘锅？",
             "锅烧热再放油，鱼身擦干水分，下锅后不要急着翻动，中火煎至定型再翻面。"),
        ]:
            prompt = f"""评估以下回答是否紧扣用户提问（Relevance）。

用户提问: {question}

回答: {response}

评估标准:
- 1.0: 回答完全切题，直接回应用户问题
- 0.5: 回答部分相关，但包含了无关内容
- 0.0: 回答完全偏题，未回应用户问题

请打分。"""
            s = _judge(prompt)
            scores.append(s)
            print(f"  Relevance: {s:.4f}")
        avg = sum(scores) / len(scores)
        print(f"\n  平均 Relevance: {avg:.4f} (目标 >= 0.5)")
        assert avg >= 0.5
