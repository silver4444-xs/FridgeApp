"""
Phase 6: Subagents 多 Agent 协作

将 8 个单体 tool 拆分为 3 个专业子 Agent + 3 个主 Agent 直属 tool：
- recipe_expert:       菜谱推荐
- substitution_expert: 食材替换
- cooking_expert:      烹饪知识问答 (自由文本，适合非结构化知识)

注意: recipe_expert 和 substitution_expert 不使用 response_format。
ToolStrategy 在非 OpenAI/Anthropic/xAI 模型上不可靠。
子 Agent 输出由主 Agent 消费，system_prompt 格式指令已足够。
"""
import logging
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRetryMiddleware
from langchain.tools import tool

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# Shared model factory (子 Agent 共用)
# ═══════════════════════════════════════════════════════════════

def _make_model(model_name: str = None,
                temperature: float = 0.1,
                max_tokens: int = 2048,
                disable_thinking: bool = False):
    """创建子 Agent 共享的模型实例。

    disable_thinking=True: 禁用 DeepSeek thinking 模式。
    使用 response_format (Structured Output) 时必须禁 thinking，
    因为 thinking 模式下 DeepSeek 不支持 tool_choice。
    """
    import os
    import httpx
    from langchain.chat_models import init_chat_model
    if model_name is None:
        model_name = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    kwargs = dict(
        model=f"openai:{model_name}",
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        http_client=httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
        ),
    )
    if disable_thinking:
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
    return init_chat_model(**kwargs)

_model_cache = {}

def _get_model(temperature: float = 0.1, disable_thinking: bool = False):
    key = ("model", temperature, disable_thinking)
    if key not in _model_cache:
        _model_cache[key] = _make_model(temperature=temperature, disable_thinking=disable_thinking)
    return _model_cache[key]


# ═══════════════════════════════════════════════════════════════
# Subagent 1: 菜谱推荐专家
# ═══════════════════════════════════════════════════════════════
# 原代码: 3 个独立 tool — recommend_by_fridge, search_recipes_by_ingredients, get_recipe_detail
#  LLM 需自行判断何时调用哪个、如何组合结果
# 改进后: 1 个子 Agent 内部完成"分析需求→搜索→返回详情"全流程
#  主 Agent 只需传自然语言 query，子 Agent 自主决策调用哪些底层 tool

def _create_recipe_agent(model, tools, store=None, checkpointer=None):
    """内部: 创建菜谱推荐子 Agent

    注意: 不使用 response_format。
    ToolStrategy 在 DeepSeek 上不可靠 (模型不调用隐藏 Respond 工具 → 循环重试)。
    子 Agent 输出是给主 Agent 消费的，用 system_prompt 格式指令就足够了。
    """
    kwargs = {}
    if store is not None:
        kwargs["store"] = store
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
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
            "- 不要编造菜谱，始终基于工具返回的真实数据\n"
            "\n"
            "输出格式:\n"
            "- 推荐结果使用表格: | 菜名 | 主要食材 | 难度 | 时间 |\n"
            "- 每道菜附一句话亮点描述\n"
            "- 总共不超过 5 道推荐"
        ),
        middleware=[
            ModelRetryMiddleware(max_retries=2, initial_delay=0.5),
        ],
        **kwargs,
    )


_recipe_subagent = None
_substitution_subagent = None
_cooking_subagent = None

@tool("recipe_expert", description="菜谱推荐专家：根据食材推荐可制作的菜谱、提供详细做法和步骤。适用于「能做什么菜」「推荐几个菜」「XX菜怎么做」。")
def call_recipe_expert(query: str) -> str:
    """调用菜谱推荐子 Agent。"""
    from api.tools import (
        get_recipe_detail,
        recommend_by_fridge,
        search_recipes_by_ingredients,
    )

    global _recipe_subagent
    if _recipe_subagent is None:
        from api.tools import get_recipe_detail, recommend_by_fridge, search_recipes_by_ingredients
        from api.dependencies import fridge_store, fridge_checkpointer
        _recipe_subagent = _create_recipe_agent(
            _get_model(),
            [recommend_by_fridge, search_recipes_by_ingredients, get_recipe_detail],
            store=fridge_store,
            checkpointer=fridge_checkpointer,
        )

    try:
        result = _recipe_subagent.invoke({
            "messages": [{"role": "user", "content": query}],
        })
        if "structured_response" in result:
            return result["structured_response"].model_dump_json(indent=2, ensure_ascii=False)
        return result["messages"][-1].content
    except Exception as e:
        logger.error(f"[recipe_expert] 调用失败: {e}")
        return f"菜谱专家暂时无法响应: {str(e)[:200]}"


# ═══════════════════════════════════════════════════════════════
# Subagent 2: 食材替换专家
# ═══════════════════════════════════════════════════════════════
# 原代码: find_substitutions 独立 tool，与主 Agent 共用 LLM 实例
# 改进后: 独立子 Agent，可配置更低的 temperature (替换建议需精确)

def _create_substitution_agent(model, store=None, checkpointer=None):
    """内部: 创建食材替换子 Agent

    注意: 不使用 response_format (原因同 recipe_expert)。
    """
    from api.tools import find_substitutions
    kwargs = {}
    if store is not None:
        kwargs["store"] = store
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
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


@tool("substitution_expert", description="食材替换专家：为缺少的食材寻找替代方案。适用于「没有XX可以用什么代替」「XX能换成什么」。")
def call_substitution_expert(query: str) -> str:
    """调用食材替换子 Agent。"""
    global _substitution_subagent
    if _substitution_subagent is None:
        from api.dependencies import fridge_store, fridge_checkpointer
        _substitution_subagent = _create_substitution_agent(
            _get_model(temperature=0.0),
            store=fridge_store,
            checkpointer=fridge_checkpointer,
        )

    try:
        result = _substitution_subagent.invoke({
            "messages": [{"role": "user", "content": query}],
        })
        if "structured_response" in result:
            return result["structured_response"].model_dump_json(indent=2, ensure_ascii=False)
        return result["messages"][-1].content
    except Exception as e:
        logger.error(f"[substitution_expert] 调用失败: {e}")
        return f"替换专家暂时无法响应: {str(e)[:200]}"


# ═══════════════════════════════════════════════════════════════
# Subagent 3: 烹饪知识专家 (RAG)
# ═══════════════════════════════════════════════════════════════
# 原代码: search_cooking_knowledge 独立 tool
# 改进后: 子 Agent 可进行多轮知识检索（追问/澄清），而非单次问答

def _create_cooking_qa_agent(model, store=None, checkpointer=None):
    """内部: 创建烹饪知识子 Agent"""
    from api.tools import search_cooking_knowledge
    kwargs = {}
    if store is not None:
        kwargs["store"] = store
    if checkpointer is not None:
        kwargs["checkpointer"] = checkpointer
    return create_agent(
        model=model,
        tools=[search_cooking_knowledge],
        system_prompt=(
            "你是烹饪知识专家。回答烹饪技巧、食材处理、菜系知识等问题。\n\n"
            "规则:\n"
            "- 调用 search_cooking_knowledge 从知识库检索相关信息\n"
            "- 基于检索结果给出准确、实用的回答\n"
            "- 回答时引用知识来源\n"
            "- 如果知识库没有相关信息，如实告知并给出常识性建议\n"
            "\n"
            "输出格式:\n"
            "- 使用 ### 标题分隔不同主题\n"
            "- 用编号列表给出步骤或要点\n"
            "- 关键技巧用 **粗体** 标注\n"
            "- 回答控制在 300 字以内"
        ),
        middleware=[
            ModelRetryMiddleware(max_retries=2, initial_delay=0.5),
        ],
        **kwargs,
    )


@tool("cooking_expert", description="烹饪知识专家：回答烹饪技巧、食材处理方法、菜系知识等。适用于「怎么让鸡肉更嫩」「川菜有什么特点」「如何挑选西瓜」等知识性问题。")
def call_cooking_expert(query: str) -> str:
    """调用烹饪知识子 Agent。

    Args:
        query: 烹饪知识问题，如「如何让鸡肉更嫩」「煎鱼不粘锅的技巧」
    """
    global _cooking_subagent
    if _cooking_subagent is None:
        from api.dependencies import fridge_store, fridge_checkpointer
        _cooking_subagent = _create_cooking_qa_agent(
            _get_model(),
            store=fridge_store,
            checkpointer=fridge_checkpointer,
        )

    try:
        result = _cooking_subagent.invoke({
            "messages": [{"role": "user", "content": query}],
        })
        return result["messages"][-1].content
    except Exception as e:
        logger.error(f"[cooking_expert] 调用失败: {e}")
        return f"烹饪专家暂时无法响应: {str(e)[:200]}"


# ═══════════════════════════════════════════════════════════════
# 子 Agent 工具包装器列表 (供主 Agent 使用)
# ═══════════════════════════════════════════════════════════════

SUBAGENT_TOOLS = [
    call_recipe_expert,
    call_substitution_expert,
    call_cooking_expert,
]
