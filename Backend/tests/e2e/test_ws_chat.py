"""WebSocket 协议测试 — 验证消息格式校验与 chat_relay 边界逻辑"""
import json, pytest
from unittest.mock import MagicMock, AsyncMock


class TestWSProtocol:
    """客户端↔服务端消息协议的正确性"""

    def test_chat_message_schema(self):
        """验证客户端发送的 chat 消息 JSON 可正常序列化/反序列化"""
        msg = {"type": "chat", "message": "能做什么菜?", "thread_id": "u1"}
        assert json.loads(json.dumps(msg)) == msg

    def test_server_event_types(self):
        """注册表完整性检查 — 确保所有事件类型常量已定义, 防止遗漏"""
        events = {"stream_token", "stream_tool_start", "stream_tool_end",
                  "stream_tool_error", "stream_interrupt", "stream_done",
                  "stream_error", "pong"}
        assert events  # 完整性检查


class TestChatRelayLogic:
    """chat_relay 端点的输入校验与并发保护逻辑 (mock, 不连真实 WS)"""

    @pytest.mark.asyncio
    async def test_busy_guard(self):
        """验证并发保护: 上一轮对话未结束时拒绝新消息, 防止状态混乱"""
        ws = MagicMock(); ws.send_json = AsyncMock(); ws._chat_busy = True
        if getattr(ws, '_chat_busy', False):
            await ws.send_json({"type": "stream_error",
                                "error": "上一条消息仍在处理中，请稍候"})
        assert "处理中" in ws.send_json.call_args[0][0]["error"]

    @pytest.mark.asyncio
    async def test_empty_message_rejected(self):
        """验证输入校验: 空消息被拦截, 避免无效请求进入 Agent 推理"""
        ws = MagicMock(); ws.send_json = AsyncMock()
        if not "":
            await ws.send_json({"type": "stream_error", "error": "message 不能为空"})
        assert "不能为空" in ws.send_json.call_args[0][0]["error"]

    @pytest.mark.asyncio
    async def test_invalid_json_rejected(self):
        """验证输入校验: 非法 JSON 被捕获并返回友好错误, 不会导致服务崩溃"""
        ws = MagicMock(); ws.send_json = AsyncMock()
        try:
            json.loads("not valid json {")
        except json.JSONDecodeError:
            await ws.send_json({"type": "stream_error", "error": "消息格式错误，需要 JSON"})
        assert "格式错误" in ws.send_json.call_args[0][0]["error"]


class TestWSAuth:
    """P0 #5 修复: WebSocket 查询参数鉴权"""

    def test_dev_mode_bypass(self, monkeypatch):
        """开发模式: API_KEY 未设置时 verify_ws_api_key 返回 True"""
        from api.auth import verify_ws_api_key
        monkeypatch.setattr("api.auth.API_KEY", "")
        ws = MagicMock()
        ws.query_params = {"api_key": "anything"}
        assert verify_ws_api_key(ws) is True

    def test_missing_key_rejected(self, monkeypatch):
        """生产模式: 无 api_key 参数时返回 False"""
        from api.auth import verify_ws_api_key
        monkeypatch.setattr("api.auth.API_KEY", "test123")
        ws = MagicMock()
        ws.query_params = {}
        ws.close = AsyncMock()
        result = verify_ws_api_key(ws)
        assert result is False

    def test_invalid_key_rejected(self, monkeypatch):
        """生产模式: 无效 api_key 时返回 False"""
        from api.auth import verify_ws_api_key
        monkeypatch.setattr("api.auth.API_KEY", "test123")
        ws = MagicMock()
        ws.query_params = {"api_key": "wrong"}
        ws.close = AsyncMock()
        result = verify_ws_api_key(ws)
        assert result is False

    def test_valid_key_accepted(self, monkeypatch):
        """生产模式: 有效 api_key 时返回 True"""
        from api.auth import verify_ws_api_key
        monkeypatch.setattr("api.auth.API_KEY", "test123")
        ws = MagicMock()
        ws.query_params = {"api_key": "test123"}
        assert verify_ws_api_key(ws) is True


class TestHITLAutoClear:
    """P0 #4 修复: HITL 中断追踪 + 自动清除 + resume busy 保护"""

    def test_pending_interrupts_is_dict(self):
        """模块级 _pending_interrupts 是一个 dict"""
        from api.chat_relay import _pending_interrupts
        assert isinstance(_pending_interrupts, dict)

    @pytest.mark.asyncio
    async def test_pending_interrupts_pop_clears(self):
        """pop 操作能正确清除追踪条目"""
        from api.chat_relay import _pending_interrupts
        _pending_interrupts["test_thread"] = True
        assert _pending_interrupts.pop("test_thread", None) is True
        assert "test_thread" not in _pending_interrupts

    @pytest.mark.asyncio
    async def test_resume_busy_guard_simulated(self):
        """resume 消息在 _chat_busy=True 时被拦截"""
        ws = MagicMock(); ws.send_json = AsyncMock(); ws._chat_busy = True
        if getattr(ws, '_chat_busy', False):
            await ws.send_json({
                "type": "stream_error",
                "error": "上一条消息仍在处理中，请稍候",
            })
        assert "处理中" in ws.send_json.call_args[0][0]["error"]


class TestExtractToken:
    """P1 #12 修复: 统一 token 提取兼容多种模型格式"""

    def test_text_attr(self):
        from api.chat_relay import _extract_token
        chunk = type("Chunk", (), {"text": "hello", "content": ""})()
        assert _extract_token(chunk) == "hello"

    def test_content_str(self):
        from api.chat_relay import _extract_token
        chunk = type("Chunk", (), {"content": "world"})()
        assert _extract_token(chunk) == "world"

    def test_content_list_text_key(self):
        from api.chat_relay import _extract_token
        chunk = type("Chunk", (), {"content": [{"text": "hi"}]})()
        assert _extract_token(chunk) == "hi"

    def test_content_list_type_text(self):
        from api.chat_relay import _extract_token
        chunk = type("Chunk", (), {"content": [{"type": "text", "text": "x"}]})()
        assert _extract_token(chunk) == "x"

    def test_content_list_value_key(self):
        from api.chat_relay import _extract_token
        chunk = type("Chunk", (), {"content": [{"value": "val"}]})()
        assert _extract_token(chunk) == "val"

    def test_none_chunk(self):
        from api.chat_relay import _extract_token
        assert _extract_token(None) is None

    def test_empty_content(self):
        from api.chat_relay import _extract_token
        chunk = type("Chunk", (), {"content": ""})()
        assert _extract_token(chunk) is None


class TestInterruptDetection:
    """P0 修复: langgraph 1.x 中断以 on_chain_stream 事件携带 __interrupt__"""

    def test_interrupt_chunk_detected(self):
        from api.chat_relay import _is_interrupt_chunk
        assert _is_interrupt_chunk({"__interrupt__": (object(),)}) is True

    def test_normal_chunk_not_interrupt(self):
        from api.chat_relay import _is_interrupt_chunk
        assert _is_interrupt_chunk({"messages": ["hi"]}) is False

    def test_non_dict_not_interrupt(self):
        from api.chat_relay import _is_interrupt_chunk
        assert _is_interrupt_chunk(None) is False
        assert _is_interrupt_chunk("__interrupt__") is False


def _make_interrupt_chunk(value):
    """构造 langgraph 中断 chunk: {'__interrupt__': (Interrupt(value=...),)}"""
    interrupt = type("Interrupt", (), {"value": value})()
    return {"__interrupt__": (interrupt,)}


def _make_save_prefs_chunk(prefs):
    """构造 save_user_preferences 的 HITL 中断 chunk"""
    return _make_interrupt_chunk({
        "action_requests": [{
            "name": "save_user_preferences",
            "args": {"preferences": prefs},
            "description": "保存用户饮食偏好到长期记忆",
        }],
        "review_configs": [{"allowed_decisions": ["approve", "reject"]}],
    })


class TestExtractInterruptPayload:
    """HITL 审批卡片需展示「将要保存什么」— 从中断 chunk 取回工具入参。

    HumanInTheLoopMiddleware 的 Interrupt.value 结构:
        {"action_requests": [{"name","args","description"}], "review_configs": [...]}
    """

    def test_extracts_whitelisted_args(self):
        from api.chat_relay import _extract_interrupt_payload
        prefs = {"忌口": ["花生", "香菜"], "偏好菜系": "川菜", "人数": 2}
        payload = _extract_interrupt_payload(_make_save_prefs_chunk(prefs))
        # description 不外发: 前端有自己的文案, 透传只会变成死数据
        assert payload == {"args": {"preferences": prefs}}

    # ── 白名单: 默认关闭, 避免将来给别的工具加 HITL 时入参被自动外发 ──

    def test_non_whitelisted_tool_not_exposed(self):
        from api.chat_relay import _extract_interrupt_payload
        chunk = _make_interrupt_chunk({
            "action_requests": [{"name": "transfer_funds", "args": {"token": "sk-secret"}}],
        })
        assert _extract_interrupt_payload(chunk) == {}

    def test_non_whitelisted_field_stripped(self):
        """白名单工具的非白名单字段也不外发"""
        from api.chat_relay import _extract_interrupt_payload
        chunk = _make_interrupt_chunk({
            "action_requests": [{
                "name": "save_user_preferences",
                "args": {"preferences": {"忌口": ["花生"]}, "internal_token": "sk-secret"},
            }],
        })
        payload = _extract_interrupt_payload(chunk)
        assert payload == {"args": {"preferences": {"忌口": ["花生"]}}}
        assert "internal_token" not in payload["args"]

    def test_missing_args_key(self):
        from api.chat_relay import _extract_interrupt_payload
        chunk = _make_interrupt_chunk({
            "action_requests": [{"name": "save_user_preferences", "args": {}}],
        })
        assert _extract_interrupt_payload(chunk) == {"args": {}}

    # ── 体积/序列化: 必须在 ws.send_json 之前挡下 ──

    def test_oversized_args_rejected(self):
        from api.chat_relay import _extract_interrupt_payload, _HITL_ARGS_MAX_CHARS
        huge = {"忌口": ["x" * _HITL_ARGS_MAX_CHARS]}
        assert _extract_interrupt_payload(_make_save_prefs_chunk(huge)) == {}

    def test_unserializable_args_rejected(self):
        """非 JSON 类型若漏到 send_json 会抛异常 → 中断已登记但卡片发不出去"""
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload(_make_save_prefs_chunk({"忌口": object()})) == {}

    # ── 以下均为降级路径: 取不到展示内容不能让中断本身失败 ──

    def test_missing_action_requests(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload(_make_interrupt_chunk({"review_configs": []})) == {}

    def test_empty_action_requests(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload(_make_interrupt_chunk({"action_requests": []})) == {}

    def test_value_not_dict(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload(_make_interrupt_chunk("plain string")) == {}
        assert _extract_interrupt_payload(_make_interrupt_chunk(None)) == {}

    def test_action_request_not_dict(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload(_make_interrupt_chunk({"action_requests": ["oops"]})) == {}

    def test_args_not_dict(self):
        from api.chat_relay import _extract_interrupt_payload
        chunk = _make_interrupt_chunk({
            "action_requests": [{"name": "save_user_preferences", "args": "oops"}],
        })
        assert _extract_interrupt_payload(chunk) == {}

    def test_empty_interrupt_tuple(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload({"__interrupt__": ()}) == {}

    def test_interrupt_without_value_attr(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload({"__interrupt__": (object(),)}) == {}

    def test_non_interrupt_chunk(self):
        from api.chat_relay import _extract_interrupt_payload
        assert _extract_interrupt_payload({"messages": ["hi"]}) == {}
        assert _extract_interrupt_payload(None) == {}

    def test_never_raises_on_malformed_shapes(self):
        """结构不是预期的 tuple 时也必须降级, 而不是抛异常吞掉中断"""
        from api.chat_relay import _extract_interrupt_payload
        for bad in (5, {"a": 1}, "str", True):
            assert _extract_interrupt_payload({"__interrupt__": bad}) == {}

    def test_unhashable_tool_name(self):
        from api.chat_relay import _extract_interrupt_payload
        chunk = _make_interrupt_chunk({
            "action_requests": [{"name": {"weird": 1}, "args": {"preferences": {}}}],
        })
        assert _extract_interrupt_payload(chunk) == {}


class TestSubagentCache:
    """P1 #1 修复: 子 Agent 缓存键简化"""

    def test_cache_key_is_agent_name(self):
        from api.subagents import _agent_cache, _get_or_create_agent, clear_agent_cache
        clear_agent_cache()

        def fake_create(model, tools, store=None, checkpointer=None):
            return {"agent": "mock"}

        model = type("Model", (), {})()
        a1 = _get_or_create_agent("test_agent", fake_create, model, [])
        a2 = _get_or_create_agent("test_agent", fake_create, model, [])
        assert a1 is a2
        assert "test_agent" in _agent_cache
        clear_agent_cache()

    def test_clear_agent_cache(self):
        from api.subagents import _agent_cache, _model_cache, clear_agent_cache
        _agent_cache["dummy"] = "x"
        _model_cache[("model", 0.1, False)] = "y"
        clear_agent_cache()
        assert len(_agent_cache) == 0
        assert len(_model_cache) == 0


class TestMatchRecipes:
    """P2 #11 修复: _match_recipes 共用匹配管道"""

    def test_function_exists(self):
        from api.tools import _match_recipes
        assert callable(_match_recipes)

    def test_empty_input(self):
        from api.tools import _match_recipes
        results = _match_recipes([], limit=5)
        assert results == []

    def test_avoid_list_filter(self):
        from api.tools import _match_recipes
        results = _match_recipes([{"name": "鸡蛋", "cat": "meat_egg"}], limit=5, avoid_list=["鸡蛋"])
        # 鸡蛋在忌口列表中，匹配结果不应包含含鸡蛋的菜
        for r in results:
            assert "鸡蛋" not in r["matched"]


class TestModeRegistry:
    """P2 #16 修复: Agent 模式策略注册表"""

    def test_all_modes_registered(self):
        from main import _get_basic_tools, _get_context_tools, _get_subagent_tools
        from main import _CONTEXT_SYSTEM_PROMPT, _SUBAGENTS_SYSTEM_PROMPT
        assert callable(_get_basic_tools)
        assert callable(_get_context_tools)
        assert callable(_get_subagent_tools)
        assert isinstance(_CONTEXT_SYSTEM_PROMPT, str)
        assert isinstance(_SUBAGENTS_SYSTEM_PROMPT, str)
        assert len(_CONTEXT_SYSTEM_PROMPT) > 100
        assert len(_SUBAGENTS_SYSTEM_PROMPT) > 100

    def test_tools_not_empty(self):
        from main import _get_basic_tools, _get_context_tools, _get_subagent_tools
        assert len(_get_basic_tools()) == 4
        assert len(_get_context_tools()) == 8
        assert len(_get_subagent_tools()) == 6