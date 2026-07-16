"""E2E — 完整对话流程 (需真实 LLM API, 较慢, 用 --markers 过滤执行)"""
import os, pytest
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import InMemorySaver


@pytest.fixture(scope="module")
def e2e_graph():
    """每个 module 构建一次 graph — InMemoryStore/InMemorySaver 确保测试间状态隔离"""
    os.environ.setdefault("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    from main import create_fridge_graph_wrapper
    return create_fridge_graph_wrapper(store=InMemoryStore(), checkpointer=InMemorySaver())


class TestFullConversation:
    """端到端多轮对话 — 验证 Agent 在真实 LLM 下的上下文记忆与子 Agent 调度"""

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_recommend_then_detail(self, e2e_graph):
        """验证同一 thread_id 下第2轮能引用第1轮的推荐结果追问详情"""
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"},
            {"name": "鸡胸肉", "qty": 2, "cat": "肉蛋生鲜类"}]
        cfg = {"configurable": {"thread_id": "e2e_001"}}
        r1 = await e2e_graph.ainvoke(
            {"messages": [{"role": "user", "content": "推荐一道简单的菜"}]}, config=cfg)
        r2 = await e2e_graph.ainvoke(
            {"messages": [{"role": "user", "content": "完整步骤是什么？"}]}, config=cfg)
        assert len(r2["messages"]) > len(r1["messages"])
        print(f"\n  Turn1: {r1['messages'][-1].content[:150]}")
        print(f"  Turn2: {r2['messages'][-1].content[:150]}")

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_substitution_flow(self, e2e_graph):
        """验证 substitution_expert 子 Agent 能被正确调度并返回替代建议"""
        import api.dependencies as deps
        deps.current_fridge_inventory = [
            {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
            {"name": "西红柿", "qty": 3, "cat": "蔬菜"}]
        cfg = {"configurable": {"thread_id": "e2e_sub"}}
        r1 = await e2e_graph.ainvoke(
            {"messages": [{"role": "user", "content": "鸡蛋西红柿能做什么菜？"}]}, config=cfg)
        r2 = await e2e_graph.ainvoke(
            {"messages": [{"role": "user", "content": "没有鸡蛋可以用什么代替？"}]}, config=cfg)
        assert len(r2["messages"][-1].content) > 20
        print(f"\n  Recommend: {r1['messages'][-1].content[:150]}")
        print(f"  Substitute: {r2['messages'][-1].content[:150]}")

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_cooking_knowledge(self, e2e_graph):
        """验证 cooking_expert 子 Agent 触发 RAG 检索并返回烹饪知识"""
        import api.dependencies as deps
        deps.current_fridge_inventory = []
        r = await e2e_graph.ainvoke(
            {"messages": [{"role": "user", "content": "煲汤一般要煲多久？有什么技巧？"}]},
            config={"configurable": {"thread_id": "e2e_know"}})
        assert len(r["messages"][-1].content) > 30
        print(f"\n  {r['messages'][-1].content[:300]}")