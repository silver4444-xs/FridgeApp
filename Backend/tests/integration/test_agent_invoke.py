"""
Agent/Graph 集成测试 — 真实 invoke (需 DeepSeek API)

测试范围:
  1. TestAgentInvoke :
     - 单轮 Agent 调用是否产生有效回复 (test_basic)
     - Agent 能否正确调用 get_fridge_inventory 工具返回食材信息 (test_inventory)
  2. TestGraphMultiTurn :
     - 相同 thread_id 的多轮对话上下文继承 (test_two_turns)
     - 不同 thread_id 的消息隔离 — 验证 Checkpointer 按 thread 分存 (test_thread_isolation)
"""
import os, pytest
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver


@pytest.fixture(scope="module")
def test_graph():
    os.environ.setdefault("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    from main import create_fridge_graph_wrapper
    return create_fridge_graph_wrapper(store=InMemoryStore(), checkpointer=InMemorySaver())


class TestAgentInvoke:
    """单轮 Agent 调用基础验证 — Agent 能否正常响应并调用工具"""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_basic(self, test_graph):
        """验证 Agent 能收到用户输入并返回非空回复 (最简单的端到端链路)"""
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 3, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 2, "cat": "蔬菜"}]
        r = await test_graph.ainvoke(
            {"messages": [{"role": "user", "content": "你好，推荐一道菜"}]},
            config={"configurable": {"thread_id": "test_basic"}})
        assert len(r["messages"]) > 0
        print(f"\n  {r['messages'][-1].content[:200]}")

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_inventory(self, test_graph):
        """验证 Agent 能正确调用 get_fridge_inventory 工具，回复中含冰箱中实际存在的食材名"""
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"}]
        r = await test_graph.ainvoke(
            {"messages": [{"role": "user", "content": "冰箱里有什么？"}]},
            config={"configurable": {"thread_id": "test_inv"}})
        content = r["messages"][-1].content.lower()
        assert "鸡蛋" in content or "egg" in content


class TestGraphMultiTurn:
    """多轮对话 + Checkpointer 持久化 — 验证上下文继承与隔离"""

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_two_turns(self, test_graph):
        """第二轮消息携带第一轮上下文 (thread_id 相同) → 第二轮 messages 数 > 第一轮"""
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"}]
        cfg = {"configurable": {"thread_id": "test_mt_001"}}
        r1 = await test_graph.ainvoke(
            {"messages": [{"role": "user", "content": "推荐一道菜"}]}, config=cfg)
        r2 = await test_graph.ainvoke(
            {"messages": [{"role": "user", "content": "具体步骤是什么？"}]}, config=cfg)
        assert len(r2["messages"]) > len(r1["messages"])

    @pytest.mark.integration
    @pytest.mark.slow
    async def test_thread_isolation(self, test_graph):
        """不同 thread_id 的对话完全隔离 — user_b 不应看到 user_a 设置的'张三'"""
        await test_graph.ainvoke(
            {"messages": [{"role": "user", "content": "我叫张三"}]},
            config={"configurable": {"thread_id": "user_a"}})
        r_b = await test_graph.ainvoke(
            {"messages": [{"role": "user", "content": "我是谁？"}]},
            config={"configurable": {"thread_id": "user_b"}})
        assert "张三" not in r_b["messages"][-1].content
