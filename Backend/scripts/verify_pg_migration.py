"""
PG 迁移验证脚本 — 直接对真实 PostgreSQL 做 AsyncPostgresStore / AsyncPostgresSaver 往返测试。

覆盖 save_user_preferences 走的同一条 store.aput/aget 代码路径，
以及会话 checkpointer 的 aput/aget 路径。确定性、无 LLM 依赖。

运行:
    cd Backend
    python scripts/verify_pg_migration.py
"""
import asyncio
import os
import sys
from contextlib import AsyncExitStack
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PG_URI = os.getenv("POSTGRES_URI")
if not PG_URI:
    print("FAIL: POSTGRES_URI 未配置")
    sys.exit(1)


async def test_store() -> bool:
    """AsyncPostgresStore aput/aget 往返 — 对应 save_user_preferences 的持久化路径。"""
    from langgraph.store.postgres.aio import AsyncPostgresStore

    stack = AsyncExitStack()
    store = await stack.enter_async_context(AsyncPostgresStore.from_conn_string(PG_URI))
    await store.setup()

    ns, key = ("preferences",), "verify_test_user"
    value = {"忌口": ["花生"], "偏好菜系": "川菜", "人数": 2}

    await store.aput(ns, key, value)
    got = await store.aget(ns, key)

    ok = got is not None and got.value == value
    print(f"[store] 写入后读回: {got.value if got else None}")
    print(f"[store] 往返一致: {'OK' if ok else 'MISMATCH'}")

    # 清理测试数据，保持 store 干净
    await store.adelete(ns, key)
    await stack.aclose()
    return ok


async def test_checkpointer() -> bool:
    """AsyncPostgresSaver aput/aget 往返 — 对应会话历史/HITL 状态的持久化路径。"""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    stack = AsyncExitStack()
    saver = await stack.enter_async_context(AsyncPostgresSaver.from_conn_string(PG_URI))
    await saver.setup()

    thread_id = "verify_cp_test"
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    checkpoint = {
        "v": 1,
        "id": "verify-cp-id",
        "ts": "2026-08-21T00:00:00.000000Z",
        "channel_values": {"messages": []},
        "channel_versions": {},
        "versions_seen": {},
    }

    await saver.aput(config, checkpoint, metadata={}, new_versions={})
    got = await saver.aget(config)

    ok = got is not None
    print(f"[checkpointer] 写入后读回: {'OK (非空)' if ok else 'NOT FOUND'}")
    await stack.aclose()
    return ok


async def main():
    results = {}
    for name, fn in (("store", test_store), ("checkpointer", test_checkpointer)):
        try:
            results[name] = await fn()
        except Exception as e:
            results[name] = False
            print(f"[{name}] FAIL: {type(e).__name__}: {e}")
    print("=== 验证结果 ===")
    for k, v in results.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    if all(results.values()):
        print("=== ALL PASS ===")
    else:
        print("=== 有 FAIL，请检查 ===")
        sys.exit(1)


if __name__ == "__main__":
    # Windows: psycopg async 不能用 ProactorEventLoop，改用 SelectorEventLoop（与 uvicorn 一致）
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
