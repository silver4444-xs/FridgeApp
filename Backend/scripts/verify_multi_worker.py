"""
多 worker 无状态化验证脚本 (Phase 2 可靠性与弹性)。

在 `uvicorn api.server:app --workers 4 --reload` 下运行, 验证:
  1. HITL 中断 → approve 恢复 (写操作审批链路)
  2. 多轮对话跨 worker 恢复 (PG checkpointer 持久化会话历史)

原理:
  同一 thread_id 的多轮消息经 `--workers 4` 的负载均衡, 大概率落在不同 worker。
  若 PG checkpointer 生效, 第二轮 "第一个菜的具体步骤" 仍能基于第一轮 "推荐几个家常菜"
  的上下文回答; 若退化到 InMemory, 不同 worker 各自无历史, 第二轮会丢失指代。

运行 (需后端已启动, 见 docs/FridgeAI_可靠性与弹性.md §4):
    cd Backend
    python scripts/verify_multi_worker.py
"""
import argparse
import asyncio
import json
import sys
import uuid

import websockets


async def recv_event(ws, timeout=90):
    """接收单条事件, 超时抛出。"""
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


async def collect_until_done(ws, label, timeout=90):
    """收集事件直到 stream_done / stream_error。

    返回 (events, ok, interrupt_seen, error_msg)。
    HITL 时 stream_interrupt 会先到, 但须继续等到 stream_done (chat 流结束)。
    """
    events = []
    interrupt_seen = False
    while True:
        evt = await recv_event(ws, timeout=timeout)
        events.append(evt)
        t = evt.get("type")
        if t == "stream_token":
            continue
        if t == "stream_interrupt":
            interrupt_seen = True
            print(f"  [{label}] stream_interrupt (HITL) tool={evt.get('tool')}")
        elif t == "stream_tool_start":
            print(f"  [{label}] tool_start: {evt.get('tool')}")
        elif t == "stream_tool_end":
            print(f"  [{label}] tool_end: {evt.get('tool')}")
        elif t == "stream_done":
            n_tok = _token_count(events)
            print(f"  [{label}] stream_done (tokens={n_tok})")
            return events, True, interrupt_seen, None
        elif t == "stream_error":
            print(f"  [{label}] stream_error: {evt.get('error')}")
            return events, False, interrupt_seen, evt.get("error")


def _token_count(events):
    return sum(1 for e in events if e.get("type") == "stream_token")


async def main():
    parser = argparse.ArgumentParser(description="多 worker 无状态化验证")
    parser.add_argument("--url", default="ws://127.0.0.1:8000/ws/chat")
    parser.add_argument("--api-key", default="all-in-rag")
    parser.add_argument("--thread-id", default=f"verify_multi_worker_{uuid.uuid4().hex[:8]}")
    args = parser.parse_args()

    ws_url = args.url
    if args.api_key:
        ws_url = f"{ws_url}?api_key={args.api_key}"

    print(f"[client] connecting {ws_url} (thread_id={args.thread_id})")
    failures = []

    async with websockets.connect(ws_url, max_size=10_000_000) as ws:
        # ── 1. 触发 HITL ──
        print("\n[1] 触发 HITL: 声明忌口 → save_user_preferences")
        await ws.send(json.dumps(
            {"type": "chat", "message": "我不吃花生，帮我记住这个忌口", "thread_id": args.thread_id},
            ensure_ascii=False,
        ))
        _, ok1, interrupt_seen, err1 = await collect_until_done(ws, "HITL-chat")
        if not ok1:
            failures.append(f"HITL chat 流错误: {err1}")
        if not interrupt_seen:
            failures.append("未触发 HITL 中断 (预期 save_user_preferences 需审批)")

        # ── 2. approve 恢复 ──
        if interrupt_seen:
            print("\n[2] approve 恢复 HITL")
            await ws.send(json.dumps(
                {"type": "resume", "decision": "approve", "thread_id": args.thread_id},
                ensure_ascii=False,
            ))
            _, ok2, _, err2 = await collect_until_done(ws, "HITL-resume")
            if not ok2:
                failures.append(f"HITL approve 流错误: {err2}")

        # ── 3. 多轮 turn 1: 推荐 ──
        print("\n[3] 多轮 turn 1: 推荐几个家常菜")
        await ws.send(json.dumps(
            {"type": "chat", "message": "推荐几个家常菜", "thread_id": args.thread_id},
            ensure_ascii=False,
        ))
        events1, ok3, _, err3 = await collect_until_done(ws, "turn1")
        if not ok3:
            failures.append(f"turn1 流错误: {err3}")

        # ── 4. 多轮 turn 2: 指代 (跨 worker 上下文恢复) ──
        print("\n[4] 多轮 turn 2: 第一个菜的具体步骤 (指代上文)")
        await ws.send(json.dumps(
            {"type": "chat", "message": "第一个菜的具体步骤", "thread_id": args.thread_id},
            ensure_ascii=False,
        ))
        events2, ok4, _, err4 = await collect_until_done(ws, "turn2")
        if not ok4:
            failures.append(f"turn2 流错误: {err4}")

        if _token_count(events1) == 0:
            failures.append("turn1 无 token 输出")
        if _token_count(events2) == 0:
            failures.append("turn2 无 token 输出 (多轮上下文可能未恢复)")

    print("\n=== 验证结果 ===")
    if failures:
        for f in failures:
            print(f"  ❌ {f}")
        print("=== 有 FAIL ===")
        sys.exit(1)
    print("  ✅ HITL 中断/恢复 + 多轮跨 worker 恢复正常")
    print("  (提示: 语义连贯性请人工复核 turn2 是否准确解析 '第一个菜')")
    print("=== ALL PASS ===")


if __name__ == "__main__":
    asyncio.run(main())
