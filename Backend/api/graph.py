"""
Phase 2: LangGraph 状态图 —— 持久化与多轮对话

将 create_agent 嵌入 LangGraph StateGraph，实现:
1. 多轮对话持久化 (InMemorySaver checkpoint)
2. thread_id 多用户隔离
3. 自定义状态字段 (current_inventory, dietary_restrictions)

原代码: 每次请求独立，无状态
改进后: StateGraph + checkpointer，支持「刚才说的第一道菜」类指代

Phase 2.1 (当前): 简单包装 —— Agent 作为单个 Node
Phase 2.2 (未来) : Prompt Chaining —— analyze→search→rank→generate
"""
import logging
from typing import List

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import AgentState

logger = logging.getLogger(__name__)


# 自定义状态模型
#   result = rag_system.ask_question_with_routing(question, stream=False)
#   通过 thread_id 隔离多用户，支持「刚才说的那道菜」等指代

class FridgeAgentState(AgentState):
    """冰箱 Agent 对话状态 —— 扩展 LangChain AgentState。

    AgentState 已内置 messages (对话历史)。
    新增字段在每次 graph invocation 时自动合并。
    """
    current_inventory: List[dict]
    """当前冰箱食材快照，由 get_fridge_inventory / recommend_by_fridge 更新"""

    dietary_restrictions: List[str]
    """用户饮食限制，如 ["花生过敏", "不吃辣"]"""


# Graph Node: Agent 推荐节点
#   def ask_question_with_routing(self, question, stream=False, ...):
#       relevant_docs, analysis = self.query_router.route_query(question, ...)
#       result = self.generation_module.generate_adaptive_answer(question, docs)
#       return result, analysis
#   Agent 自主 tool-calling，StateGraph 管理对话持久化

def _make_recommend_node(fridge_agent):
    """创建 Agent 推荐节点——将 create_agent 实例嵌入 LangGraph Node。

    Args:
        fridge_agent: create_agent() 返回的 Agent (Runnable)

    Returns:
        async node function compatible with StateGraph.add_node()
    """

    async def recommend_node(state: FridgeAgentState, config) -> dict:
        """Agent 推荐节点: 调用 Agent 处理用户消息，返回新的 messages。

        该 Node 在每次 graph.invoke() 时执行:
        1. StateGraph 从 checkpointer 恢复历史 messages
        2. 新用户消息追加到 messages 末尾
        3. Agent 处理（含 tool-calling 循环）
        4. 返回的 messages 自动持久化到 checkpointer
        """
        from api.tools import FridgeContext

        user_id = config.get("configurable", {}).get("thread_id", "default")
        result = await fridge_agent.ainvoke(
            {"messages": state["messages"]},
            context=FridgeContext(
                current_inventory=state.get("current_inventory", []),
                user_id=user_id,
            ),
        )
        return {"messages": result["messages"]}

    return recommend_node


# Graph 构建: 简单包装版本 (Phase 2.1 — 当前)

def create_fridge_graph(
    fridge_agent,
    checkpointer=None,
    store=None,
):
    """创建 LangGraph StateGraph，嵌入 create_agent 实例。

    构建 START → recommend(Agent) → END 的简单图。
    通过 InMemorySaver 自动持久化 messages，实现多轮对话。

    Args:
        fridge_agent: create_agent() 返回的 Agent 实例
        checkpointer: 检查点存储器，默认 InMemorySaver (开发)，
                      生产环境使用 PostgresSaver
        store: Long-term Memory Store，默认 None。
               工具通过 runtime.store 读写跨会话数据。
               开发用 InMemoryStore，生产用 PostgresStore。

    Returns:
        编译后的 CompiledStateGraph，支持 .invoke() / .astream() / .stream()

    使用示例:
        graph = create_fridge_graph(agent)

        # 第一轮
        result = graph.invoke(
            {"messages": [{"role": "user", "content": "能做什么菜?"}]},
            config={"configurable": {"thread_id": "user_abc"}},
        )

        # 第二轮 (自动继承上文)
        result = graph.invoke(
            {"messages": [{"role": "user", "content": "第一个菜的具体步骤?"}]},
            config={"configurable": {"thread_id": "user_abc"}},
        )
    """
    if checkpointer is None:
        checkpointer = InMemorySaver()
        logger.info("使用 InMemorySaver (开发模式)，生产环境请使用 PostgresSaver")

    # ── 构建 StateGraph ──
    # Phase 3.5: 注入 store 实现 Long-term Memory
    workflow = StateGraph(FridgeAgentState)

    # 创建 Agent 节点
    recommend_node = _make_recommend_node(fridge_agent)
    workflow.add_node("recommend", recommend_node)

    # 编排: START → recommend → END
    workflow.add_edge(START, "recommend")
    workflow.add_edge("recommend", END)

    # ── 编译 (注入 checkpointer + store 实现持久化) ──
    # Phase 3.5: 注入 store 实现 Long-term Memory (工具通过 runtime.store 读写)
    compile_kwargs = {"checkpointer": checkpointer}
    if store is not None:
        compile_kwargs["store"] = store
    graph = workflow.compile(**compile_kwargs)

    store_info = f" + Store({type(store).__name__})" if store else ""
    logger.info(f"FridgeGraph 创建完成 (StateGraph + InMemorySaver{store_info})")
    return graph


# Graph 构建: Prompt Chaining 版本 (Phase 2.2 — 未来，已注释)
# 优化推荐流程: 分析食材 → 检索菜谱 → 排序推荐 → 生成回答
# 每个步骤是独立的 LLM 调用，可单独调试和优化。
#
# 当前版本 (简单包装) 让 Agent 自主完成所有步骤;
# 当需要更精细的控制和可观测性时，启用此版本。
# from typing import TypedDict
#
# class RecommendState(TypedDict):
#     """推荐链状态 —— 每个 Node 传递的数据结构"""
#     inventory: list[dict]       # 冰箱食材
#     analyzed: dict              # 食材分析结果
#     candidates: list[dict]      # 候选菜谱
#     ranked: list[dict]          # 排序后菜谱
#     response: str               # 最终回答
#     messages: list              # 对话历史
#
#
# def _make_analyze_node(model):
#     """分析食材节点: LLM 分析冰箱库存特征"""
#     async def analyze_node(state: RecommendState) -> dict:
#         prompt = f"分析以下食材适合做什么类型的菜: {state['inventory']}"
#         response = await model.ainvoke(prompt)
#         return {"analyzed": {"categories": response.content, "count": len(state["inventory"])}}
#     return analyze_node
#
#
# def _make_search_node(model):
#     """检索菜谱节点: 基于分析结果搜索匹配菜谱"""
#     async def search_node(state: RecommendState) -> dict:
#         from api.dependencies import recipe_db, inverted_index
#         from matching.fuzzy_matcher import FuzzyMatcher
#         fridge_names = FuzzyMatcher.normalize_fridge_items(state["inventory"])
#         candidate_ids = inverted_index.fuzzy_lookup(fridge_names)
#         candidates = [recipe_db.get(rid) for rid in candidate_ids if recipe_db.get(rid)]
#         return {"candidates": candidates}
#     return search_node
#
#
# def _make_rank_node(model):
#     """排序推荐节点: LLM 按匹配度排序"""
#     async def rank_node(state: RecommendState) -> dict:
#         prompt = f"将以下菜谱按匹配度排序，top5: {state['candidates']}"
#         response = await model.ainvoke(prompt)
#         return {"ranked": state["candidates"][:5]}
#     return rank_node
#
#
# def _make_generate_node(model):
#     """生成回答节点: 格式化最终推荐结果"""
#     async def generate_node(state: RecommendState) -> dict:
#         prompt = f"基于排序结果生成推荐: {state['ranked']}"
#         response = await model.ainvoke(prompt)
#         return {"response": response.content}
#     return generate_node
#
#
# def create_fridge_graph_with_chaining(model):
#     """Prompt Chaining 版本 —— 四步推荐流水线
#
#     对比简单包装版本:
#     - 优点: 每步可独立调试、测试、替换实现
#     - 缺点: 更多 LLM 调用，延迟更高
#     - 适用场景: 需要生产级可观测性的部署
#     """
#     workflow = StateGraph(RecommendState)
#
#     workflow.add_node("analyze_inventory", _make_analyze_node(model))
#     workflow.add_node("search_recipes", _make_search_node(model))
#     workflow.add_node("rank_results", _make_rank_node(model))
#     workflow.add_node("generate_response", _make_generate_node(model))
#
#     workflow.add_edge(START, "analyze_inventory")
#     workflow.add_edge("analyze_inventory", "search_recipes")
#     workflow.add_edge("search_recipes", "rank_results")
#     workflow.add_edge("rank_results", "generate_response")
#     workflow.add_edge("generate_response", END)
#
#     return workflow.compile(checkpointer=InMemorySaver())
