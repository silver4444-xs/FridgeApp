"""
结构化日志配置 (P2-3)

提供 JSON 格式输出 + ContextVar 跨模块传递 request_id/thread_id。
所有模块的 logger 自动携带请求级上下文，无需手动拼接。

用法:
    # server.py 启动时
    from api.logging_config import setup_logging
    setup_logging()

    # chat_relay.py — 入口设置
    from api.logging_config import request_id_ctx, thread_id_ctx
    request_id_ctx.set(str(uuid.uuid4())[:8])
    thread_id_ctx.set(thread_id)

    # 所有其他模块 — 无需改动
    logger.info("开始混合检索")
"""
import json
import logging
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
thread_id_ctx: ContextVar[str] = ContextVar("thread_id", default="")


class _FridgeJsonFormatter(logging.Formatter):
    """输出带 request_id/thread_id 的结构化 JSON 日志。"""

    def format(self, record):
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "logger": record.name,
            "level": record.levelname,
            "msg": record.getMessage(),
            "req": request_id_ctx.get(),
            "thread": thread_id_ctx.get(),
        }
        if record.exc_info and record.exc_info[1]:
            entry["exc"] = str(record.exc_info[1])
        return json.dumps(entry, ensure_ascii=False)


def setup_logging(level: int = logging.INFO):
    """初始化结构化日志（应用启动时调用一次）。"""
    handler = logging.StreamHandler()
    handler.setFormatter(_FridgeJsonFormatter())
    logging.root.handlers = [handler]
    logging.root.setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("neo4j").setLevel(logging.WARNING)
