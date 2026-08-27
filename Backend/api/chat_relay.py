"""
Phase 5: 流式输出 —— Agent Chat WebSocket 端点

提供 /ws/chat 端点，实现 Agent 响应的 token 级流式推送。
支持: 打字机效果文本 + Tool call 进度 + 多轮对话 (thread_id)

原代码: 无 Agent 对话 WebSocket，仅有 OneNET 数据推送 /ws/fridge
改进后: 新增 /ws/chat，graph.astream_events(v3) 实时推送
"""
import asyncio
import json
import logging
import time
import uuid
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from api.logging_config import (
    request_id_ctx, thread_id_ctx, token_in_ctx, token_out_ctx, latency_ms_ctx,
)
from api.auth import verify_ws_api_key
from langgraph.types import Command

from config import reliability_config

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

# P0 修复: 追踪每个 thread_id 是否有未处理的 HITL 中断
_pending_interrupts: dict[str, bool] = {}

# P1-D: HITL 中断超时自动 reject
async def _schedule_interrupt_timeout(thread_id: str, timeout: float = None):
    if timeout is None:
        timeout = reliability_config.stream_event_timeout_seconds
    """HITL 中断超时后自动 reject，防止永久挂起。"""
    await asyncio.sleep(timeout)
    if _pending_interrupts.pop(thread_id, None):
        logger.warning(f"[HITL] thread={thread_id} 中断超时({timeout}s)，自动 reject")
        from api.dependencies import fridge_graph
        if fridge_graph:
            try:
                await fridge_graph.ainvoke(
                    Command(resume={"decisions": [{"type": "reject"}]}),
                    config={"configurable": {"thread_id": thread_id}},
                )
            except Exception as e:
                logger.error(f"[HITL] 自动 reject 失败: {e}")

# P2 #17: tool 中文标签，通过 stream_tool_start 传递给前端
_TOOL_LABELS = {
    "recipe_expert": "正在搜索菜谱...",
    "substitution_expert": "正在查找替换方案...",
    "cooking_expert": "正在检索烹饪知识...",
    "recommend_by_fridge": "正在分析冰箱食材...",
    "search_recipes_by_ingredients": "正在搜索菜谱...",
    "get_recipe_detail": "正在获取菜谱详情...",
    "find_substitutions": "正在查找替换食材...",
    "search_cooking_knowledge": "正在检索知识库...",
    "get_fridge_inventory": "正在读取冰箱库存...",
    "save_user_preferences": "正在保存偏好...",
    "get_user_preferences": "正在读取偏好...",
}


def _extract_token(chunk) -> str | None:
    """从 AIMessageChunk 中提取文本 token。

    P1 修复: 统一两处重复的 token 提取逻辑，兼容多种模型返回格式:
      - chunk.text 属性 (LangChain AIMessageChunk)
      - chunk.content 为 str
      - chunk.content 为 list[dict] 含 "text" / "value" / "content" key
      - chunk.content 为 list[dict] 含 {"type":"text", "text":"..."} (Anthropic/Claude 格式)
    """
    if chunk is None:
        return None
    if hasattr(chunk, "text") and chunk.text:
        return chunk.text
    if hasattr(chunk, "content"):
        c = chunk.content
        if isinstance(c, str):
            return c if c else None
        if isinstance(c, list) and c:
            first = c[0]
            if isinstance(first, dict):
                for key in ("text", "value", "content"):
                    if key in first:
                        return first[key]
            return str(first) if first else None
    return None


def _is_interrupt_chunk(chunk) -> bool:
    """langgraph 1.x 的 HITL 中断以 on_chain_stream 事件携带
    chunk = {'__interrupt__': (Interrupt(...),)} 出现（on_chain_interrupt 事件已不存在）。
    """
    return isinstance(chunk, dict) and "__interrupt__" in chunk


# HITL 审批卡片可展示的工具入参白名单: {工具名: (可暴露字段, ...)}
# 默认关闭 —— 中断入参可能含凭证/地址等敏感数据，将来给别的工具加 HITL 时
# 不应自动外发；未列出的工具让前端回退成通用文案即可。
_HITL_EXPOSED_ARGS: dict[str, tuple[str, ...]] = {
    "save_user_preferences": ("preferences",),
}

# args 由 LLM 生成、长度不可控，与本文件其他字段(error[:300]/output[:500])一样需上限
_HITL_ARGS_MAX_CHARS = 2000


def _extract_interrupt_payload(chunk) -> dict:
    """从中断 chunk 取出待审批操作的入参，供前端展示「将要保存什么」。

    HumanInTheLoopMiddleware 抛出的 Interrupt.value 是 HITLRequest:
        {"action_requests": [{"name","args","description"?}], "review_configs": [...]}
    其中 args 即工具入参，如 {"preferences": {"忌口": ["花生"], "偏好菜系": "川菜"}}。
    仅透传 _HITL_EXPOSED_ARGS 白名单内的工具与字段。

    Returns:
        {"args": dict}，任一环节不满足则返回 {}。
        本函数不抛异常 —— 取不到展示内容只该让卡片回退成通用文案，绝不能连累
        中断本身失败(那会让 save_user_preferences 等不到审批，只能靠超时自动 reject)。
    """
    try:
        if not _is_interrupt_chunk(chunk):
            return {}
        interrupts = chunk["__interrupt__"]
        if not interrupts:
            return {}
        value = getattr(interrupts[0], "value", None)
        if not isinstance(value, dict):
            return {}
        requests = value.get("action_requests")
        if not isinstance(requests, list) or not requests:
            return {}
        first = requests[0]
        if not isinstance(first, dict):
            return {}
        exposed = _HITL_EXPOSED_ARGS.get(first.get("name"))
        if not exposed:
            return {}
        raw_args = first.get("args")
        if not isinstance(raw_args, dict):
            return {}
        args = {k: raw_args[k] for k in exposed if k in raw_args}
        # 预校验可序列化与体积: 若留到 ws.send_json 才抛，中断已登记但
        # stream_interrupt 发不出去 → 审批卡片永远不出现。
        if len(json.dumps(args, ensure_ascii=False)) > _HITL_ARGS_MAX_CHARS:
            return {}
        return {"args": args}
    except Exception:
        logger.debug("[HITL] 中断入参提取失败，卡片回退通用文案", exc_info=True)
        return {}


async def _handle_and_release(ws: WebSocket, message: str, thread_id: str):
    """包装 _handle_chat_stream，完成后自动释放 _chat_busy 标记。"""
    try:
        await _handle_chat_stream(ws, message, thread_id)
    finally:
        ws._chat_busy = False


async def _handle_chat_stream(ws: WebSocket, message: str, thread_id: str):
    """核心流式处理：调用 graph.astream_events(v2) 并逐 token 推送给客户端。

    v2 返回标准 AsyncIterator，支持 anext() + asyncio.wait_for 超时控制。

    Args:
        ws: WebSocket 连接
        message: 用户消息文本
        thread_id: 对话线程 ID (用于多轮对话持久化)
    """
    try:
        from api.dependencies import fridge_graph

        if not fridge_graph:
            await ws.send_json({
                "type": "stream_error",
                "error": "Agent 未初始化，请稍后重试",
            })
            return

        config = {"configurable": {"thread_id": thread_id}}

        # 获取冰箱当前食材快照，注入 Agent context
        from api.dependencies import get_current_inventory
        inventory = get_current_inventory()

        logger.info(f"[Chat Stream] Starting graph for thread={thread_id}")
        stream = fridge_graph.astream_events(
            {
                "messages": [{"role": "user", "content": message}],
                "current_inventory": inventory,
            },
            config=config,
            version="v2",
            # 注意: 不能用 include_types 过滤。
            # langgraph 1.2.8 的 include_types 会吞掉 on_chain_stream(__interrupt__) 事件
            # （HITL 中断依赖该事件才被客户端感知），且会连带丢弃流式 token。
            # 事件类型过滤由下方 if/elif 分发完成，无需在此预过滤。
        )

        # ── P1-C: 可观测性追踪 ──
        t_start = time.monotonic()
        token_count = 0

        current_tool: str | None = None
        deadline = time.monotonic() + reliability_config.stream_total_timeout_seconds

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError("Agent 响应超时")
            try:
                event = await asyncio.wait_for(
                    anext(stream),
                    timeout=min(remaining, reliability_config.stream_event_timeout_seconds),
                )
            except StopAsyncIteration:
                break

            event_type = event.get("event", "")

            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                token = _extract_token(chunk)
                if token:
                        token_count += 1  # P1-C: 流式 token 计数
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
                    "label": _TOOL_LABELS.get(current_tool, current_tool),
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

            # ── Tool 调用错误 ──
            elif event_type == "on_tool_error":
                error_tool = event.get("name", "unknown")
                error_msg = str(event.get("data", {}).get("error", "未知错误"))
                logger.warning(f"[Chat Stream] Tool error: {error_tool} — {error_msg[:200]}")
                await ws.send_json({
                    "type": "stream_tool_error",
                    "tool": error_tool,
                    "error": error_msg[:300],
                })
                current_tool = None

            elif event_type == "on_chain_stream":
                # P0 修复: langgraph 1.x 中断以 on_chain_stream 事件携带
                # chunk = {"__interrupt__": (Interrupt(...),)}，标记该 thread 有未处理中断
                chunk = event.get("data", {}).get("chunk")
                if _is_interrupt_chunk(chunk):
                    _pending_interrupts[thread_id] = True
                    # P1-D: 启动 30s 超时定时器，超时自动 reject
                    asyncio.create_task(_schedule_interrupt_timeout(thread_id))
                    # args 供前端展示「将要保存什么」，取不到则为空 → 前端回退通用文案
                    payload = _extract_interrupt_payload(chunk)
                    await ws.send_json({
                        "type": "stream_interrupt",
                        "tool": current_tool or "unknown",
                        "interrupt_type": "hitl",
                        "args": payload.get("args", {}),
                    })

        # ── P1-C: 记录延迟和 token 到可观测性 ContextVar ──
        latency_ms_ctx.set(int((time.monotonic() - t_start) * 1000))
        token_out_ctx.set(token_count)
        logger.info(f"[Chat Stream] thread={thread_id} done: "
                     f"tokens={token_count}, latency={latency_ms_ctx.get()}ms")

        await ws.send_json({"type": "stream_done"})

    except asyncio.TimeoutError:
        logger.warning(f"[Chat Stream] Timeout for thread={thread_id}")
        await ws.send_json({
            "type": "stream_error",
            "error": "AI 响应超时，请简化问题或稍后重试",
        })
    except Exception as e:
        logger.error(f"[Chat Stream] Error for thread={thread_id}: {e}")
        await ws.send_json({
            "type": "stream_error",
            "error": f"流式处理出错: {str(e)}",
        })


async def _handle_chat_resume(ws: WebSocket, thread_id: str, decision: str):
    """处理 HITL resume (approve/reject)，流式推送恢复后的执行结果。

    P0 修复: 替代原来 ws_chat 中内联的 resume 处理。
    - 添加 asyncio.wait_for 超时保护 (30s per event, 60s total)
    - 处理全部事件类型 (含 tool_error / interrupt)
    - finally 清除 _pending_interrupts 追踪
    """
    from api.dependencies import fridge_graph

    config = {"configurable": {"thread_id": thread_id}}
    deadline = time.monotonic() + reliability_config.stream_total_timeout_seconds

    try:
        if not fridge_graph:
            await ws.send_json({
                "type": "stream_error",
                "error": "Agent 未初始化，请稍后重试",
            })
            return

        if decision == "reject":
            result = await fridge_graph.ainvoke(
                Command(resume={"decisions": [{"type": "reject"}]}),
                config=config,
            )
            await ws.send_json({
                "type": "stream_done",
                "reply": result["messages"][-1].content if result.get("messages") else "已拒绝该操作。",
            })
        else:
            # 流式恢复审批后的执行
            stream = fridge_graph.astream_events(
                Command(resume={"decisions": [{"type": "approve"}]}),
                config=config,
                version="v2",
            )
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError("Resume 响应超时")
                try:
                    event = await asyncio.wait_for(
                        anext(stream),
                        timeout=min(remaining, reliability_config.stream_event_timeout_seconds),
                    )
                except StopAsyncIteration:
                    break

                ev = event.get("event", "")

                if ev == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    token = _extract_token(chunk)
                    if token:
                            await ws.send_json({"type": "stream_token", "token": token})

                elif ev == "on_tool_start":
                    await ws.send_json({
                        "type": "stream_tool_start",
                        "tool": event.get("name", "unknown"),
                        "input": event.get("data", {}).get("input", {}),
                    })

                elif ev == "on_tool_end":
                    out = event.get("data", {}).get("output")
                    await ws.send_json({
                        "type": "stream_tool_end",
                        "tool": event.get("name", "unknown"),
                        "output": str(out)[:500] if out else "",
                    })

                elif ev == "on_tool_error":
                    await ws.send_json({
                        "type": "stream_tool_error",
                        "tool": event.get("name", "unknown"),
                        "error": str(event.get("data", {}).get("error", ""))[:300],
                    })

                elif ev == "on_chain_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if _is_interrupt_chunk(chunk):
                        _pending_interrupts[thread_id] = True
                        payload = _extract_interrupt_payload(chunk)
                        await ws.send_json({
                            "type": "stream_interrupt",
                            "tool": event.get("name", "unknown"),
                            "interrupt_type": "hitl",
                            "args": payload.get("args", {}),
                        })

            await ws.send_json({"type": "stream_done"})

    except asyncio.TimeoutError:
        logger.warning(f"[Chat Resume] Timeout for {thread_id}")
        await ws.send_json({
            "type": "stream_error",
            "error": "Resume 响应超时，请重试",
        })
    except Exception as e:
        logger.error(f"[Chat Resume] Error for {thread_id}: {e}")
        await ws.send_json({
            "type": "stream_error",
            "error": f"恢复执行失败: {str(e)}",
        })
    finally:
        _pending_interrupts.pop(thread_id, None)


async def _handle_resume_and_release(ws: WebSocket, thread_id: str, decision: str):
    """包装 _handle_chat_resume，统一 _chat_busy 标记管理。"""
    try:
        await _handle_chat_resume(ws, thread_id, decision)
    finally:
        ws._chat_busy = False


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
    # P0 修复: WebSocket 查询参数鉴权
    if not verify_ws_api_key(websocket):
        return
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

                # 设置请求级日志上下文 (P2-3)
                request_id_ctx.set(str(uuid.uuid4())[:8])
                thread_id_ctx.set(thread_id)

                # ── 改进后 (asyncio.create_task 并发): ──
                # 每条消息用独立 Task 处理，不阻塞消息接收循环
                # _chat_busy 标记防止同一连接并发重叠（保持 thread_id 对话顺序）
                if not message:
                    await websocket.send_json({
                        "type": "stream_error",
                        "error": "message 不能为空",
                    })
                    continue

                if getattr(websocket, '_chat_busy', False):
                    await websocket.send_json({
                        "type": "stream_error",
                        "error": "上一条消息仍在处理中，请稍候",
                    })
                    continue

                # P0 修复: 自动取消该 thread 的未完成 HITL 中断
                if _pending_interrupts.pop(thread_id, None):
                    try:
                        from api.dependencies import fridge_graph
                        if fridge_graph:
                            await fridge_graph.ainvoke(
                                Command(resume={"decisions": [{"type": "reject"}]}),
                                config={"configurable": {"thread_id": thread_id}},
                            )
                        logger.info(f"[Chat WS] Auto-cleared interrupt for {thread_id}")
                    except Exception as e:
                        logger.warning(f"[Chat WS] Failed to clear interrupt for {thread_id}: {e}")

                websocket._chat_busy = True
                logger.info(f"[Chat WS] thread={thread_id}, msg='{message[:50]}...'")
                asyncio.create_task(
                    _handle_and_release(websocket, message, thread_id)
                )

            elif msg_type == "resume":
                thread_id = data.get("thread_id", "default")
                decision = data.get("decision", "approve")

                request_id_ctx.set(str(uuid.uuid4())[:8])
                thread_id_ctx.set(thread_id)

                # P0 修复: _chat_busy 保护 + async task 调度
                if getattr(websocket, '_chat_busy', False):
                    await websocket.send_json({
                        "type": "stream_error",
                        "error": "上一条消息仍在处理中，请稍候",
                    })
                    continue

                websocket._chat_busy = True
                logger.info(f"[Chat WS] Resume {decision} for thread={thread_id}")
                asyncio.create_task(
                    _handle_resume_and_release(websocket, thread_id, decision)
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            else:
                await websocket.send_json({
                    "type": "stream_error",
                    "error": f"未知消息类型: {msg_type}",
                })

    except WebSocketDisconnect:
        # P1-D: WS 断连时清理所有 pending interrupts（避免内存泄漏）
        cleaned = 0
        for tid in list(_pending_interrupts):
            if _pending_interrupts.pop(tid, None):
                cleaned += 1
        if cleaned:
            logger.info(f"[Chat WS] Disconnected, cleaned {cleaned} pending interrupts")
        else:
            logger.info("[Chat WS] Client disconnected")
    except Exception as e:
        logger.error(f"[Chat WS] Unexpected error: {e}")
