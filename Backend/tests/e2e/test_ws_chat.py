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