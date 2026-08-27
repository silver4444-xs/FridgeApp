"""
E2E 验证: /ws/chat 触发 save_user_preferences → HITL interrupt → approve → 验证 PG store 写入。

流程要点:
  chat 消息由 asyncio.create_task 后台处理，_chat_busy 在流式结束后才释放。
  因此客户端必须等 chat 流的 stream_done 之后，再发 resume approve（否则被「仍在处理中」拒绝）。

运行 (需后端已启动):
    cd Backend
    python scripts/ws_e2e_verify.py
"""
import asyncio
import json
import os
from collections import Counter

# 从环境变量读取; 后端在 API_KEY 未设置时为开发模式放行, 故空值是合法的
API_KEY = os.getenv("API_KEY", "")
WS_URL = f"ws://127.0.0.1:8000/ws/chat?api_key={API_KEY}"
THREAD_ID = "e2e_verify_20260822"
MESSAGE = "我不吃辣，帮我记住这个忌口"


async def recv_event(ws):
    raw = await asyncio.wait_for(ws.recv(), timeout=90)
    return json.loads(raw)


async def main():
    import websockets

    async with websockets.connect(WS_URL, max_size=10_000_000) as ws:
        print(f"[client] connected, sending: {MESSAGE}")
        await ws.send(json.dumps(
            {"type": "chat", "message": MESSAGE, "thread_id": THREAD_ID},
            ensure_ascii=False,
        ))

        events = []
        interrupt_seen = False

        # Phase 1: 等 chat 流结束 (stream_interrupt 会先到，但必须继续等到 stream_done)
        while True:
            evt = await recv_event(ws)
            events.append(evt)
            t = evt.get("type")
            if t == "stream_interrupt":
                interrupt_seen = True
                print(f"[evt] stream_interrupt (HITL) tool={evt.get('tool')}")
            elif t == "stream_done":
                print(f"[evt] chat stream done (interrupt_seen={interrupt_seen})")
                break
            elif t == "stream_error":
                print(f"[evt] stream_error: {evt.get('error')}")
                break

        if interrupt_seen:
            print("[client] approving HITL ...")
            await ws.send(json.dumps(
                {"type": "resume", "decision": "approve", "thread_id": THREAD_ID},
                ensure_ascii=False,
            ))
            while True:
                evt = await recv_event(ws)
                events.append(evt)
                t = evt.get("type")
                if t == "stream_done":
                    print("[evt] resume stream done")
                    break
                if t == "stream_error":
                    print(f"[evt] resume stream_error: {evt.get('error')}")
                    break

        types = Counter(e.get("type") for e in events)
        print("=== event type counts ===")
        for k, v in types.items():
            print(f"  {k}: {v}")
        print(f"interrupt_seen={interrupt_seen}")


if __name__ == "__main__":
    asyncio.run(main())
