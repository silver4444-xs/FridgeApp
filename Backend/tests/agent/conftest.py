"""
Agent 测试 conftest — 初始化 fridge_agent 单例

在测试中绕过 FastAPI lifespan，直接调用 main.create_fridge_agent()
创建 Agent（agent_mode="subagents"），注入到 api.dependencies。
"""
import os
import sys
import pytest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dotenv import load_dotenv
load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def init_agent():
    """session 级别: 初始化 fridge_agent 单例，所有 agent 测试共享。"""
    import api.dependencies as deps

    if deps.fridge_agent is not None:
        return deps.fridge_agent

    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set — cannot initialize Agent")

    from main import create_fridge_agent
    from langgraph.store.memory import InMemoryStore
    from langgraph.checkpoint.memory import InMemorySaver

    store = InMemoryStore()
    checkpointer = InMemorySaver()

    agent = create_fridge_agent(
        model_name=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
        temperature=0.0,
        max_tokens=2048,
        store=store,
        checkpointer=checkpointer,
        agent_mode="subagents",
    )

    deps.fridge_agent = agent
    deps.fridge_store = store
    deps.fridge_checkpointer = checkpointer

    return agent
