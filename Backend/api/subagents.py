"""
Phase 6 + Phase 8: Subagents 多 Agent 协作 + Structured Output

将 8 个单体 tool 拆分为 3 个专业子 Agent + 3 个主 Agent 直属 tool：
- recipe_expert:       菜谱推荐 + 结构化输出 (AgentRecommendResponse)
- substitution_expert: 食材替换 + 结构化输出 (AgentSubstitutionResponse)
- cooking_expert:      烹饪知识问答 (自由文本，适合非结构化知识)

Phase 8: recipe_expert 和 substitution_expert 使用 response_format
  LangChain 自动选择 ProviderStrategy 或 ToolStrategy
  结构化结果以 JSON 字符串返回给主 Agent
"""
import logging
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain.tools import tool

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Shared model factory (子 Agent 共用)
# ═══════════════════════════════════════════════════════════════

def _make_model(model_name: str = "deepseek-v4-flash",
                temperature: float = 0.1,
                max_tokens: int = 2048):
    """创建子 Agent 共享的模型实例。"""
    import os
    from langchain.chat_models import init_chat_model
    return init_chat_model(
        f"openai:{model_name}",
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base="https://api.deepseek.com/v1",
    )


# ═══════════════════════════════════════════════════════════════
# Subagent 1: 菜谱推荐专家
# ═══════════════════════════════════════════════════════════════
# 原代码: 3 个独立 tool — recommend_by_fridge, search_recipes_by_ingredients, get_recipe_detail
#  LLM 需自行判断何时调用哪个、如何组合结果
# 改进后: 1 个子 Agent 内部完成"分析需求→搜索→返回详情"全流程
#  主 Agent 只需传自然语言 query，子 Agent 自主决策调用哪些底层 tool

def _create_recipe_agent(model, tools, response_format=None):
    """内部: 创建菜谱推荐子 Agent"""
    kwargs = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    return create_agent(
        model=model,
        tools=tools,
        system_prompt=(
            "你是菜谱推荐专家。根据用户需求推荐最适合的菜谱。\n\n"
            "能力:\n"
            "- 基于冰箱食材自动推荐可制作的菜谱\n"
            "- 根据指定食材搜索匹配菜谱\n"
            "- 提供菜谱的详细做法、食材清单和小贴士\n\n"
            "规则:\n"
            "- 优先基于冰箱当前食材推荐 (recommend_by_fridge)\n"
            "- 如果用户指定了具体食材，使用 search_recipes_by_ingredients\n"
            "- 用户想看某道菜的做法时，调用 get_recipe_detail\n"
            "- 返回结果时标注每道菜的匹配食材数和缺少的食材\n"
            "- 优先推荐匹配度高的菜谱\n"
            "- 不要编造菜谱，始终基于工具返回的真实数据"
        ),
        middleware=[
            ModelRetryMiddleware(max_retries=2, initial_delay=0.5),
        ],
        **kwargs,
    )


@tool("recipe_expert", description="菜谱推荐专家：根据食材推荐可制作的菜谱、提供详细做法和步骤。返回结构化 JSON (含菜名/匹配数/缺少食材/难度/时间)。适用于「能做什么菜」「推荐几个菜」「XX菜怎么做」。")
def call_recipe_expert(query: str) -> str:
    """调用菜谱推荐子 Agent。

    Args:
        query: 用户的菜谱相关需求，如「冰箱里能做什么菜」「推荐3道川菜」「红烧肉怎么做」
    """
    from api.tools import (
        get_recipe_detail,
        recommend_by_fridge,
        search_recipes_by_ingredients,
    )
    from api.models import AgentRecommendResponse

    # ── 原代码: ──
    # subagent = _create_recipe_agent(model, sub_tools)
    # result = subagent.invoke(...)
    # return result["messages"][-1].content  # 自由文本
    #
    # ── 改进后 (Phase 8: Structured Output): ──
    # response_format=AgentRecommendResponse → LangChain 自动选择策略
    # result["structured_response"] → AgentRecommendResponse 实例 → JSON 字符串
    model = _make_model()
    sub_tools = [recommend_by_fridge, search_recipes_by_ingredients, get_recipe_detail]
    subagent = _create_recipe_agent(model, sub_tools, response_format=AgentRecommendResponse)
    result = subagent.invoke({
        "messages": [{"role": "user", "content": query}],
    })

    # 优先返回结构化结果，回退到自由文本
    if "structured_response" in result:
        return result["structured_response"].model_dump_json(indent=2, ensure_ascii=False)
    return result["messages"][-1].content


# ═══════════════════════════════════════════════════════════════
# Subagent 2: 食材替换专家
# ═══════════════════════════════════════════════════════════════
# 原代码: find_substitutions 独立 tool，与主 Agent 共用 LLM 实例
# 改进后: 独立子 Agent，可配置更低的 temperature (替换建议需精确)

def _create_substitution_agent(model, response_format=None):
    """内部: 创建食材替换子 Agent"""
    from api.tools import find_substitutions
    kwargs = {}
    if response_format is not None:
        kwargs["response_format"] = response_format
    return create_agent(
        model=model,
        tools=[find_substitutions],
        system_prompt=(
            "你是食材替换专家。当用户缺少某食材时，提供可行的替代方案。\n\n"
            "规则:\n"
            "- 建议 2-3 种替代方案\n"
            "- 说明每种替代对口味和口感的影响\n"
            "- 优先推荐冰箱中已有的食材作为替代品\n"
            "- 如果用户提供了上下文（准备做什么菜），结合菜品特点给出建议"
        ),
        middleware=[
            ModelRetryMiddleware(max_retries=2, initial_delay=0.5),
        ],
        **kwargs,
    )


@tool("substitution_expert", description="食材替换专家：为缺少的食材寻找替代方案，返回结构化 JSON (含原食材/替代品/影响说明)。适用于「没有XX可以用什么代替」「XX能换成什么」。")
def call_substitution_expert(query: str) -> str:
    """调用食材替换子 Agent。

    Args:
        query: 食材替换需求，如「没有黄油可以用什么代替」「做红烧肉缺料酒怎么办」
    """
    from api.models import AgentSubstitutionResponse

    # ── 原代码: ──
    # model = _make_model(temperature=0.0)
    # subagent = _create_substitution_agent(model)
    # result = subagent.invoke(...)
    # return result["messages"][-1].content  # 自由文本
    #
    # ── 改进后 (Phase 8: Structured Output): ──
    # response_format=AgentSubstitutionResponse
    # temperature=0.0 确保高确定性 + 结构化保证格式一致
    model = _make_model(temperature=0.0)
    subagent = _create_substitution_agent(model, response_format=AgentSubstitutionResponse)
    result = subagent.invoke({
        "messages": [{"role": "user", "content": query}],
    })

    if "structured_response" in result:
        return result["structured_response"].model_dump_json(indent=2, ensure_ascii=False)
    return result["messages"][-1].content


# ═══════════════════════════════════════════════════════════════
# Subagent 3: 烹饪知识专家 (RAG)
# ═══════════════════════════════════════════════════════════════
# 原代码: search_cooking_knowledge 独立 tool
# 改进后: 子 Agent 可进行多轮知识检索（追问/澄清），而非单次问答

def _create_cooking_qa_agent(model):
    """内部: 创建烹饪知识子 Agent"""
    from api.tools import search_cooking_knowledge
    return create_agent(
        model=model,
        tools=[search_cooking_knowledge],
        system_prompt=(
            "你是烹饪知识专家。回答烹饪技巧、食材处理、菜系知识等问题。\n\n"
            "规则:\n"
            "- 调用 search_cooking_knowledge 从知识库检索相关信息\n"
            "- 基于检索结果给出准确、实用的回答\n"
            "- 回答时引用知识来源\n"
            "- 如果知识库没有相关信息，如实告知并给出常识性建议"
        ),
        middleware=[
            ModelRetryMiddleware(max_retries=2, initial_delay=0.5),
        ],
    )


@tool("cooking_expert", description="烹饪知识专家：回答烹饪技巧、食材处理方法、菜系知识等。适用于「怎么让鸡肉更嫩」「川菜有什么特点」「如何挑选西瓜」等知识性问题。")
def call_cooking_expert(query: str) -> str:
    """调用烹饪知识子 Agent。

    Args:
        query: 烹饪知识问题，如「如何让鸡肉更嫩」「煎鱼不粘锅的技巧」
    """
    # ── 原代码: 主 Agent 直接调用 search_cooking_knowledge ──
    # ── 改进后: 子 Agent 可多轮检索 + 追问澄清 ──
    model = _make_model()
    subagent = _create_cooking_qa_agent(model)
    result = subagent.invoke({
        "messages": [{"role": "user", "content": query}],
    })
    return result["messages"][-1].content


# ═══════════════════════════════════════════════════════════════
# 子 Agent 工具包装器列表 (供主 Agent 使用)
# ═══════════════════════════════════════════════════════════════

SUBAGENT_TOOLS = [
    call_recipe_expert,
    call_substitution_expert,
    call_cooking_expert,
]
