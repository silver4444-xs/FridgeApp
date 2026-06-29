"""
FastAPI 依赖注入 — 全局单例
被 api/server.py 和 api/routes/* 调用
"""
from matching.recipe_database import RecipeDatabase
from matching.inverted_index import InvertedIndex

recipe_db: RecipeDatabase = RecipeDatabase()
inverted_index: InvertedIndex = InvertedIndex()
rag_system = None

# ── Phase 1: Agent 标准化 —— Agent 全局单例 ──
# 在 server.py lifespan 中 RAG 系统初始化后创建
# create_agent(model, tools=FRIDGE_TOOLS, system_prompt=...)
fridge_agent = None

# ── Phase 2: LangGraph StateGraph —— Graph 全局单例 ──
# 在 server.py lifespan 中 Agent 创建后构建
# create_fridge_graph(agent, checkpointer=InMemorySaver())
fridge_graph = None

# ── Phase 3.5: Long-term Memory —— Store 全局单例 ──
# InMemoryStore: 开发模式，生产环境替换为 PostgresStore
# 在 server.py lifespan 中创建并注入 create_fridge_agent()
fridge_store = None

# ── Phase 4: HITL —— Checkpointer 全局单例 ──
# HumanInTheLoopMiddleware 依赖 checkpointer 保存中断状态
# Agent 和 Graph 共享同一实例
fridge_checkpointer = None


def get_recipe_db() -> RecipeDatabase:
    return recipe_db


def get_inverted_index() -> InvertedIndex:
    return inverted_index


def get_rag_system():
    return rag_system


def get_fridge_agent():
    """获取 LangChain Agent (create_agent 实例)"""
    return fridge_agent


def get_fridge_graph():
    """获取 LangGraph StateGraph (CompiledStateGraph 实例)

    支持多轮对话持久化:
        graph = get_fridge_graph()
        config = {"configurable": {"thread_id": "user_abc"}}
        result = graph.invoke({"messages": [...]}, config=config)
    """
    return fridge_graph


def get_fridge_store():
    """获取 LangGraph InMemoryStore (Long-term Memory)

    跨会话持久化用户偏好:
        store = get_fridge_store()
        prefs = store.get(("preferences",), "user_abc")
    """
    return fridge_store
