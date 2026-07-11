"""FridgeContext → ToolRuntime 上下文传播 + Middleware 配置验证"""
from unittest.mock import MagicMock


# ─── FridgeContext 数据类: 默认值 + ToolRuntime 上下文传播 ───
class TestFridgeContext:
    def test_defaults(self):
        """FridgeContext 默认值: user_id="default", current_inventory=[]"""
        from api.tools import FridgeContext
        ctx = FridgeContext()
        assert ctx.user_id == "default" and ctx.current_inventory == []

    def test_tool_runtime_reads_context(self):
        """ToolRuntime.context 传播: get_fridge_inventory 通过 runtime.context 读取冰箱食材"""
        from api.tools import get_fridge_inventory, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(
            current_inventory=[{"name": "鸡蛋", "qty": 1, "cat": "肉蛋"}], user_id="u1")
        import json
        r = json.loads(get_fridge_inventory.func(runtime))
        assert r["items"][0]["name"] == "鸡蛋"


# ─── Agent 创建: 3种模式 (basic/context/subagents) 均能成功实例化 ───
class TestMiddlewareConfig:
    def test_agent_creation_all_modes(self):
        """3种 agent_mode 下 create_fridge_agent() 均返回非空 Agent"""
        from main import create_fridge_agent
        from langgraph.store.memory import InMemoryStore
        from langgraph.checkpoint.memory import InMemorySaver
        for mode in ["basic", "context", "subagents"]:
            agent = create_fridge_agent(
                agent_mode=mode, store=InMemoryStore(), checkpointer=InMemorySaver())
            assert agent is not None