"""
千问交叉验证模块。

对 DeepSeek 生成的评测数据候选集, 用千问 (Qwen) 独立评分 (1-5)。
剔除评分 1-3 的低质量条目, 只保留 4-5 的高质量条目。
"""

import json
import os
import re
from typing import List, Dict, Tuple

import httpx
from langchain.chat_models import init_chat_model
from langchain.schema import HumanMessage, SystemMessage

CROSS_VALIDATION_SYSTEM_PROMPT = """你是一个评测数据质量审核专家。你需要对 RAG 评测数据条目进行质量评分。

## 评分维度 (每项 1-5 分)

1. **问题自然度**: 问题是否像真实用户会问的? 是否口语化?
2. **答案准确性**: ground_truth 是否正确、完整? 是否有编造?
3. **知识库相关性**: 答案内容是否可能在烹饪知识库中找到?

## 评分标准

- 5分: 完美。问题自然、答案准确、内容应能在知识库中找到
- 4分: 良好。基本满足要求, 有小瑕疵
- 3分: 勉强可用。有较明显问题但方向对
- 2分: 有错误。答案有编造或问题不自然
- 1分: 不可用。完全编造或问题无意义

## 输出格式

对每条输入, 输出一个 JSON:
```json
{
  "overall_score": 4,
  "question_naturalness": 4,
  "answer_accuracy": 5,
  "kb_relevance": 4,
  "reason": "问题口语化自然, 答案准确, 内容属于常见烹饪知识"
}
```

只输出 JSON 对象, 不要添加额外解释。"""


def _extract_first_json(text: str) -> str:
    """从文本中提取第一个 JSON 对象。"""
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    m = re.search(r'\{[\s\S]*?\}', text)
    return m.group(0) if m else text


def cross_validate_with_qwen(
    items: List[Dict],
    api_key: str = None,
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model_name: str = "qwen-plus",
) -> List[Tuple[Dict, float]]:
    """
    用千问对候选条目逐条评分。

    Args:
        items: 候选评测数据列表
        api_key: 千问 API Key (默认从 QWEN_API_KEY 环境变量读取)
        api_base: 千问 API Base URL
        model_name: 千问模型名 (qwen-plus 性价比最优)

    Returns:
        [(item, overall_score), ...] 按分数降序排列
    """
    api_key = api_key or os.getenv("QWEN_API_KEY")
    if not api_key:
        print("[Qwen CV] QWEN_API_KEY 未设置, 跳过交叉验证, 所有条目标记为 score=3")
        return [(item, 3.0) for item in items]

    llm = init_chat_model(
        f"openai:{model_name}",
        temperature=0.0, max_tokens=512,
        openai_api_key=api_key, openai_api_base=api_base,
        http_client=httpx.Client(timeout=httpx.Timeout(connect=10, read=60, write=10, pool=10)))

    scored = []
    for i, item in enumerate(items):
        prompt = f"""请评估以下评测数据条目:

问题: {item.get('question', '')}
参考答案: {item.get('ground_truth', '')}
类别: {item.get('category', '')}
难度: {item.get('difficulty', '')}"""

        messages = [
            SystemMessage(content=CROSS_VALIDATION_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        try:
            response = llm.invoke(messages)
            text = response.content if hasattr(response, 'content') else str(response)
            result = json.loads(_extract_first_json(text))
            score = result.get("overall_score", 3)
            scored.append((item, score))
            print(f"  [{i+1}/{len(items)}] score={score} - {item.get('question', '')[:40]}")
        except Exception as e:
            print(f"  [{i+1}/{len(items)}] 评分失败: {e}, 默认 score=3")
            scored.append((item, 3.0))

    scored.sort(key=lambda x: x[1], reverse=True)
    above_4 = sum(1 for _, s in scored if s >= 4.0)
    print(f"\n千问交叉验证完成: {above_4}/{len(scored)} 条 score >= 4.0")
    return scored
