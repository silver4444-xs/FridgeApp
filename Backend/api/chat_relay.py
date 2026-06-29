"""
Phase 5: 流式输出 —— Agent Chat WebSocket 端点

提供 /ws/chat 端点，实现 Agent 响应的 token 级流式推送。
支持: 打字机效果文本 + Tool call 进度 + 多轮对话 (thread_id)

原代码: 无 Agent 对话 WebSocket，仅有 OneNET 数据推送 /ws/fridge
改进后: 新增 /ws/chat，graph.astream_events(v3) 实时推送
"""
import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()

# ═══════════════════════════════════════════════════════════════
# WS 消息协议 (Phase 5 新增)
# ═══════════════════════════════════════════════════════════════
# Client → Server:
#   {"type": "chat",    "message": "...", "thread_id": "user_abc"}
#   {"type": "ping"}
#
# Server → Client:
#   {"type": "stream_token",      "token": "您"}                  # LLM 文本 token
#   {"type": "stream_tool_start", "tool": "recommend", "input":{}} # Tool 开始
#   {"type": "stream_tool_delta", "tool": "...","delta":"..."}     # Tool 输出片段
#   {"type": "stream_tool_end",   "tool": "...","output":"..."}    # Tool 完成
#   {"type": "stream_done"}                                        # 响应结束
#   {"type": "stream_error",      "error": "..."}                  # 错误
# ═══════════════════════════════════════════════════════════════


async def _handle_chat_stream(ws: WebSocket, message: str, thread_id: str):
    """核心流式处理：调用 graph.astream_events 并逐 token 推送给客户端。

    v3 astream_events 在 async 下不支持 interleave()（该方法仅 sync 可用），
    改用原始事件迭代：on_chat_model_stream → token, on_tool_start/end → 进度。

    Args:
        ws: WebSocket 连接
        message: 用户消息文本
        thread_id: 对话线程 ID (用于多轮对话持久化)
    """
    from api.dependencies import fridge_graph

    if not fridge_graph:
        await ws.send_json({
            "type": "stream_error",
            "error": "Agent 未初始化，请稍后重试",
        })
        return

    config = {"configurable": {"thread_id": thread_id}}

    try:
        # ── 原代码: ──
        # result = graph.invoke({"messages": [...]}, config=config)
        # 阻塞等待完整结果，前端 3-5 秒无反馈
        #
        # ── 改进后: graph.astream_events(v3) ──
        # 原始事件迭代，token 级实时推送 + Tool call 进度可见
        stream = await fridge_graph.astream_events(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
            version="v3",
        )

        current_tool: str | None = None

        async for event in stream:
            event_type = event.get("event", "")

            # ── LLM token 流 ──
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    token = None
                    # AIMessageChunk: 优先取 .text 属性
                    if hasattr(chunk, "text"):
                        token = chunk.text
                    # 或有 .content (str / list[dict])
                    elif hasattr(chunk, "content"):
                        c = chunk.content
                        if isinstance(c, str):
                            token = c
                        elif isinstance(c, list) and c and isinstance(c[0], dict):
                            token = c[0].get("text", "")
                    if token:
                        await ws.send_json({
                            "type": "stream_token",
                            "token": token,
                        })

            # ── Tool 调用开始 ──
            elif event_type == "on_tool_start":
                current_tool = event.get("name", "unknown")
                tool_input = event.get("data", {}).get("input", {})
                await ws.send_json({
                    "type": "stream_tool_start",
                    "tool": current_tool,
                    "input": tool_input,
                })

            # ── Tool 调用结束 ──
            elif event_type == "on_tool_end":
                tool_output = event.get("data", {}).get("output")
                output_str = ""
                if tool_output is not None:
                    if hasattr(tool_output, "content"):
                        output_str = str(tool_output.content)
                    else:
                        output_str = str(tool_output)
                await ws.send_json({
                    "type": "stream_tool_end",
                    "tool": current_tool or "unknown",
                    "output": output_str[:500],  # 截断过长输出
                })
                current_tool = None

        # 流结束
        await ws.send_json({"type": "stream_done"})

    except Exception as e:
        logger.error(f"[Chat Stream] Error for thread={thread_id}: {e}")
        await ws.send_json({
            "type": "stream_error",
            "error": f"流式处理出错: {str(e)}",
        })


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    """Agent 对话 WebSocket 端点 —— 流式输出。

    连接: ws://<host>:8000/ws/chat

    使用示例 (前端):
        const ws = uni.connectSocket({url: getWsBase() + '/ws/chat'})
        ws.onMessage((e) => {
            const data = JSON.parse(e.data)
            if (data.type === 'stream_token') {
                appendToChat(data.token)  // 打字机效果
            } else if (data.type === 'stream_tool_start') {
                showToolStatus(`正在调用 ${data.tool}`)
            } else if (data.type === 'stream_done') {
                endChat()
            }
        })
        ws.send({data: JSON.stringify({
            type: 'chat', message: '能做什么菜?', thread_id: 'user_abc'
        })})

    多轮对话: 在 chat 消息中传入相同 thread_id 即可继承上文。
    """
    await websocket.accept()
    logger.info("[Chat WS] Client connected")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "stream_error",
                    "error": "消息格式错误，需要 JSON",
                })
                continue

            msg_type = data.get("type", "")

            if msg_type == "chat":
                message = data.get("message", "")
                thread_id = data.get("thread_id", "default")
                if not message:
                    await websocket.send_json({
                        "type": "stream_error",
                        "error": "message 不能为空",
                    })
                    continue
                logger.info(f"[Chat WS] thread={thread_id}, msg='{message[:50]}...'")
                await _handle_chat_stream(websocket, message, thread_id)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({
                    "type": "stream_error",
                    "error": f"未知消息类型: {msg_type}",
                })

    except WebSocketDisconnect:
        logger.info("[Chat WS] Client disconnected")
    except Exception as e:
        logger.error(f"[Chat WS] Unexpected error: {e}")
