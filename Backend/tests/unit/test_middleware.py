"""
CircuitBreakerMiddleware 和中间件工厂的单元测试。

P0修复验证:
  - CircuitBreakerMiddleware 状态机: CLOSED → OPEN → HALF_OPEN → CLOSED
  - create_fridge_middleware(): 主Agent 6层 / 子Agent 4层
  - Per-tool 隔离: 工具A失败不影响工具B
  - _is_error_result: 检测 ToolMessage(status="error") + JSON {"success": false}
"""
import json
import time
import threading
import pytest
from unittest.mock import MagicMock

from langchain_core.messages import ToolMessage


# ═══════════════════════════════════════════════════════════════
# CircuitBreakerMiddleware 状态机测试
# ═══════════════════════════════════════════════════════════════

class TestCircuitBreakerStateMachine:
    """CircuitBreakerMiddleware 状态机: CLOSED → OPEN → HALF_OPEN → CLOSED"""

    @pytest.fixture
    def cb(self):
        from api.middleware import CircuitBreakerMiddleware
        return CircuitBreakerMiddleware(
            failure_threshold=3,
            cooldown_seconds=0.5,  # 短冷却便于测试
        )

    @pytest.fixture
    def make_request(self):
        """创建模拟 ToolCallRequest。"""
        def _make(tool_name="test_tool", tool_id="call_001"):
            request = MagicMock()
            request.tool_call = {"name": tool_name, "args": {}, "id": tool_id}
            return request
        return _make

    def _success_handler(self, request, content="ok"):
        """返回成功 ToolMessage 的 handler。"""
        return ToolMessage(
            content=content,
            tool_call_id=request.tool_call.get("id", ""),
        )

    def _error_handler(self, request):
        """返回 error status ToolMessage 的 handler。"""
        return ToolMessage(
            content="模拟工具执行失败",
            tool_call_id=request.tool_call.get("id", ""),
            status="error",
        )

    def _failing_handler(self, request):
        """直接抛异常的 handler。"""
        raise ConnectionError("Neo4j 连接失败")

    # ── 基本状态转换 ──

    def test_initial_state_closed(self, cb, make_request):
        """新实例：所有工具状态为 CLOSED"""
        state = cb._get_state("test_tool")
        assert state["circuit_state"] == "CLOSED", "初始状态应为 CLOSED"
        assert state["failures"] == 0, "初始失败计数应为 0"

    def test_three_failures_opens_circuit(self, cb, make_request):
        """3 次连续异常 → OPEN"""
        req = make_request()
        for i in range(3):
            with pytest.raises(ConnectionError):
                cb.wrap_tool_call(req, self._failing_handler)

        state = cb._get_state("test_tool")
        assert state["circuit_state"] == "OPEN", f"3 次失败后应为 OPEN，实际 {state['circuit_state']}"
        assert state["failures"] == 3

    def test_open_returns_error_immediately(self, cb, make_request):
        """OPEN + 冷却中 → 返回 ToolMessage error，不调用 handler"""
        req = make_request()

        # 先触发 3 次失败 → OPEN
        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.wrap_tool_call(req, self._failing_handler)

        # OPEN 状态下调用 → 应快速失败
        handler_called = threading.Event()
        def tracked(req):
            handler_called.set()
            return self._success_handler(req)

        result = cb.wrap_tool_call(req, tracked)
        assert not handler_called.is_set(), "OPEN 状态不应调用 handler"
        assert isinstance(result, ToolMessage), "应返回 ToolMessage"
        assert result.status == "error", "ToolMessage status 应为 error"
        assert "熔断" in result.content or "不可用" in result.content, \
            f"错误消息应包含熔断提示，实际: {result.content}"

    def test_after_cooldown_goes_half_open(self, cb, make_request, monkeypatch):
        """冷却期满 → HALF_OPEN，允许 1 次探测"""
        req = make_request()

        # 触发 OPEN
        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.wrap_tool_call(req, self._failing_handler)

        assert cb._get_state("test_tool")["circuit_state"] == "OPEN"

        # 快进时间（保存原始引用避免递归）
        orig_time = time.time
        monkeypatch.setattr(time, 'time', lambda: orig_time() + 0.6)

        # 探测调用 → handler 应被执行
        handler_called = threading.Event()
        def tracked(req):
            handler_called.set()
            return self._success_handler(req)

        cb.wrap_tool_call(req, tracked)
        assert handler_called.is_set(), "冷却期满后 HALF_OPEN 应调用 handler"

    def test_half_open_success_closes(self, cb, make_request, monkeypatch):
        """HALF_OPEN 探测成功 → CLOSED（恢复）"""
        req = make_request()

        # 触发 OPEN
        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.wrap_tool_call(req, self._failing_handler)

        # 快进 → HALF_OPEN 探测成功
        orig_time = time.time
        monkeypatch.setattr(time, 'time', lambda: orig_time() + 0.6)
        cb.wrap_tool_call(req, self._success_handler)

        state = cb._get_state("test_tool")
        assert state["circuit_state"] == "CLOSED", f"HALF_OPEN 探测成功 → CLOSED，实际 {state['circuit_state']}"
        assert state["failures"] == 0, "成功后失败计数应归零"

    def test_half_open_failure_reopens(self, cb, make_request, monkeypatch):
        """HALF_OPEN 探测失败 → 回 OPEN"""
        req = make_request()
        cb.failure_threshold = 1  # 让 HALF_OPEN 的 1 次失败就触发 OPEN

        # 先触发 OPEN（threshold=1）
        with pytest.raises(ConnectionError):
            cb.wrap_tool_call(req, self._failing_handler)

        # 快进
        orig_time = time.time
        monkeypatch.setattr(time, 'time', lambda: orig_time() + 0.6)

        # HALF_OPEN 探测失败
        with pytest.raises(ConnectionError):
            cb.wrap_tool_call(req, self._failing_handler)

        state = cb._get_state("test_tool")
        assert state["circuit_state"] == "OPEN", f"HALF_OPEN 探测失败 → OPEN，实际 {state['circuit_state']}"

    # ── 计数器重置 ──

    def test_success_before_threshold_resets(self, cb, make_request):
        """2 次失败 + 1 次成功 = 计数器归零"""
        req = make_request()

        with pytest.raises(ConnectionError):
            cb.wrap_tool_call(req, self._failing_handler)
        with pytest.raises(ConnectionError):
            cb.wrap_tool_call(req, self._failing_handler)

        assert cb._get_state("test_tool")["failures"] == 2

        # 第 3 次成功
        cb.wrap_tool_call(req, self._success_handler)

        state = cb._get_state("test_tool")
        assert state["failures"] == 0, f"成功后计数器应归零，实际 {state['failures']}"
        assert state["circuit_state"] == "CLOSED"

    # ── Per-tool 隔离 ──

    def test_per_tool_isolation(self, cb, make_request):
        """工具 A 的失败不影响工具 B"""
        req_a = make_request("tool_a")
        req_b = make_request("tool_b")

        # tool_a 3 次失败 → OPEN
        for _ in range(3):
            with pytest.raises(ConnectionError):
                cb.wrap_tool_call(req_a, self._failing_handler)

        assert cb._get_state("tool_a")["circuit_state"] == "OPEN"
        assert cb._get_state("tool_b")["circuit_state"] == "CLOSED"

        # tool_b 仍可正常工作
        result = cb.wrap_tool_call(req_b, self._success_handler)
        assert result.content == "ok", "tool_b 不应受 tool_a 熔断影响"

    # ── _is_error_result 检测 ──

    def test_toolmessage_error_detected(self, cb, make_request):
        """ToolMessage(status="error") 被 _is_error_result 检测"""
        req = make_request()

        # 3 次 ToolMessage error → OPEN
        for i in range(3):
            result = cb.wrap_tool_call(req, self._error_handler)
            assert result.status == "error"

        assert cb._get_state("test_tool")["circuit_state"] == "OPEN", \
            "3 次 error ToolMessage 应触发熔断"

    def test_json_success_false_detected(self, cb, make_request):
        """ToolMessage 内容 {"success": false} 被检测为错误"""
        req = make_request()

        def json_error_handler(r):
            return ToolMessage(
                content=json.dumps({"success": False, "error": "知识库未就绪"}),
                tool_call_id=r.tool_call["id"],
            )

        for _ in range(3):
            cb.wrap_tool_call(req, json_error_handler)

        assert cb._get_state("test_tool")["circuit_state"] == "OPEN", \
            "3 次 JSON success=false 应触发熔断"

    # ── 非监控工具透传 ──

    def test_untracked_tool_bypasses(self, cb, make_request):
        """不在 monitored_tools 中的工具不经过熔断器"""
        cb.monitored_tools = {"tracked_tool"}  # 只监控 tracked_tool

        req = make_request("untracked_tool")
        handler_called = threading.Event()

        def tracked(req):
            handler_called.set()
            return self._success_handler(req)

        # 连续失败不应该影响 untracked_tool
        for _ in range(5):
            result = cb.wrap_tool_call(req, tracked)
        assert handler_called.is_set(), "非监控工具应每次都被调用"
        assert "untracked_tool" not in cb._state, "非监控工具不应有状态"


# ═══════════════════════════════════════════════════════════════
# 中间件工厂测试
# ═══════════════════════════════════════════════════════════════

class TestMiddlewareFactory:
    """create_fridge_middleware() 工厂函数测试"""

    @pytest.fixture
    def mock_model(self):
        """创建假的 ChatModel。"""
        return MagicMock()

    @pytest.fixture
    def mock_tools(self):
        """创建假的工具列表（含 name 属性）。"""
        t1 = MagicMock()
        t1.name = "get_fridge_inventory"
        t2 = MagicMock()
        t2.name = "search_recipes_by_ingredients"
        t3 = MagicMock()
        t3.name = "recommend_by_fridge"
        return [t1, t2, t3]

    def test_main_agent_gets_7_layers(self, mock_model, mock_tools):
        """主 Agent 模式返回 7 个中间件（含 P1 InputGuard）"""
        from api.middleware import create_fridge_middleware

        middleware = create_fridge_middleware(
            model=mock_model,
            tools=mock_tools,
            agent_type="main",
        )
        assert len(middleware) == 7, f"主 Agent 应返回 7 层，实际 {len(middleware)} 层"

    def test_subagent_gets_4_layers(self, mock_model, mock_tools):
        """子 Agent 模式返回 4 个中间件（无 Summarization + HITL）"""
        from api.middleware import create_fridge_middleware

        middleware = create_fridge_middleware(
            model=mock_model,
            tools=mock_tools,
            agent_type="subagent",
        )
        assert len(middleware) == 4, f"子 Agent 应返回 4 层，实际 {len(middleware)} 层"

    def test_circuit_breaker_is_first(self, mock_model, mock_tools):
        """CircuitBreakerMiddleware 在 index 0"""
        from api.middleware import create_fridge_middleware, CircuitBreakerMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="main",
        )
        assert isinstance(middleware[0], CircuitBreakerMiddleware), \
            f"index 0 应为 CircuitBreakerMiddleware，实际 {type(middleware[0]).__name__}"

    def test_main_model_call_limit_15(self, mock_model, mock_tools):
        """主 Agent run_limit=15"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import ModelCallLimitMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="main",
        )
        mcl = middleware[2]  # index 2 = ModelCallLimit (index 1 is InputGuard P1)
        assert isinstance(mcl, ModelCallLimitMiddleware)
        assert mcl.run_limit == 15, f"主 Agent run_limit 应为 15，实际 {mcl.run_limit}"

    def test_subagent_model_call_limit_10(self, mock_model, mock_tools):
        """子 Agent run_limit=10"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import ModelCallLimitMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="subagent",
        )
        mcl = middleware[1]
        assert isinstance(mcl, ModelCallLimitMiddleware)
        assert mcl.run_limit == 10, f"子 Agent run_limit 应为 10，实际 {mcl.run_limit}"

    def test_model_retry_has_jitter(self, mock_model, mock_tools):
        """ModelRetryMiddleware jitter=True"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import ModelRetryMiddleware

        for agent_type in ("main", "subagent"):
            middleware = create_fridge_middleware(
                model=mock_model, tools=mock_tools, agent_type=agent_type,
            )
            mr = [m for m in middleware if isinstance(m, ModelRetryMiddleware)][0]
            assert mr.jitter is True, f"{agent_type} ModelRetryMiddleware 应有 jitter"

    def test_all_tools_covered_by_retry(self, mock_model, mock_tools):
        """ToolRetryMiddleware._tool_filter 覆盖传入的 tools"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import ToolRetryMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="main",
        )
        tr = [m for m in middleware if isinstance(m, ToolRetryMiddleware)][0]
        expected = {t.name for t in mock_tools}
        # ToolRetryMiddleware 将工具名存储在 _tool_filter 中
        actual = set(tr._tool_filter) if tr._tool_filter else set()
        assert expected.issubset(actual) or actual == expected, \
            f"ToolRetryMiddleware 应覆盖全部工具名，expected={expected}, actual={actual}"

    def test_subagent_no_summarization(self, mock_model, mock_tools):
        """子 Agent 不含 SummarizationMiddleware"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import SummarizationMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="subagent",
        )
        assert not any(isinstance(m, SummarizationMiddleware) for m in middleware), \
            "子 Agent 不应包含 SummarizationMiddleware"

    def test_subagent_no_hitl(self, mock_model, mock_tools):
        """子 Agent 不含 HumanInTheLoopMiddleware"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import HumanInTheLoopMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="subagent",
        )
        assert not any(isinstance(m, HumanInTheLoopMiddleware) for m in middleware), \
            "子 Agent 不应包含 HumanInTheLoopMiddleware"

    def test_main_has_summarization(self, mock_model, mock_tools):
        """主 Agent 含 SummarizationMiddleware"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import SummarizationMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="main",
        )
        assert any(isinstance(m, SummarizationMiddleware) for m in middleware), \
            "主 Agent 应包含 SummarizationMiddleware"

    def test_main_has_hitl(self, mock_model, mock_tools):
        """主 Agent 含 HumanInTheLoopMiddleware"""
        from api.middleware import create_fridge_middleware
        from langchain.agents.middleware import HumanInTheLoopMiddleware

        middleware = create_fridge_middleware(
            model=mock_model, tools=mock_tools, agent_type="main",
        )
        assert any(isinstance(m, HumanInTheLoopMiddleware) for m in middleware), \
            "主 Agent 应包含 HumanInTheLoopMiddleware"


# ═══════════════════════════════════════════════════════════════
# 线程安全测试
# ═══════════════════════════════════════════════════════════════

class TestCircuitBreakerThreadSafety:
    """CircuitBreakerMiddleware 并发安全性"""

    def test_concurrent_state_updates(self):
        """并发状态更新不抛异常、不丢计数"""
        from api.middleware import CircuitBreakerMiddleware

        # 高阈值确保所有调用都经过 handler（不会因熔断而 fast-fail）
        cb = CircuitBreakerMiddleware(failure_threshold=20, cooldown_seconds=1.0)

        errors = []

        def worker(tool_name, iterations):
            req = MagicMock()
            req.tool_call = {"name": tool_name, "args": {}, "id": f"call_{tool_name}"}
            for _ in range(iterations):
                try:
                    cb.wrap_tool_call(req, lambda r: (_ for _ in ()).throw(ConnectionError("fail")))
                except ConnectionError:
                    pass
                except Exception as e:
                    errors.append(e)

        threads = []
        for i in range(4):
            t = threading.Thread(target=worker, args=(f"tool_{i}", 10))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"并发操作不应抛异常: {errors}"

        # 每个工具应记录 10 次失败（没达到阈值20，状态保持 CLOSED）
        for i in range(4):
            state = cb._get_state(f"tool_{i}")
            assert state["circuit_state"] == "CLOSED", f"tool_{i} 未达阈值应为 CLOSED"
            assert state["failures"] == 10, f"tool_{i} 应有 10 次失败计数"


# ═══════════════════════════════════════════════════════════════
# 集成: 工厂 + 缓存兼容
# ═══════════════════════════════════════════════════════════════

class TestFactoryIntegration:
    """工厂与现有组件的集成验证"""

    def test_factory_compatible_with_create_agent(self):
        """工厂返回的中间件列表可传给 create_agent（无 model 时 subagent 不崩溃）"""
        from api.middleware import create_fridge_middleware

        t = MagicMock()
        t.name = "test_tool"
        middleware = create_fridge_middleware(
            model=None, tools=[t], agent_type="subagent",
        )
        assert len(middleware) == 4

    def test_circuit_breaker_tools_match_retry_tools_subset(self):
        """熔断器工具白名单是全局工具的子集"""
        from api.middleware import _CIRCUIT_BREAKER_TOOLS, _ALL_TOOL_NAMES

        missing = set(_CIRCUIT_BREAKER_TOOLS) - set(_ALL_TOOL_NAMES)
        assert len(missing) == 0, \
            f"熔断器中的工具不应在全局列表中缺失: {missing}"
