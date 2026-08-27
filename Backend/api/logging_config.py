"""
结构化日志配置 (P2-3)

提供 JSON 格式输出 + ContextVar 跨模块传递 request_id/thread_id。
所有模块的 logger 自动携带请求级上下文，无需手动拼接。

控制台默认输出「人类友好」的彩色格式 (LOG_FORMAT=pretty)：按 level 着色、
省略空的 req/thread、logger 名只保留最后一段、时间到秒。
需要机器采集/管道时设 LOG_FORMAT=json 切回结构化 JSON。

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
import os
from contextvars import ContextVar

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
thread_id_ctx: ContextVar[str] = ContextVar("thread_id", default="")
# P1-C: 可观测性 — token 计数和延迟追踪
token_in_ctx: ContextVar[int] = ContextVar("token_in", default=0)
token_out_ctx: ContextVar[int] = ContextVar("token_out", default=0)
latency_ms_ctx: ContextVar[int] = ContextVar("latency_ms", default=0)


class _FridgeJsonFormatter(logging.Formatter):
    """输出带 request_id/thread_id 的结构化 JSON 日志 (LOG_FORMAT=json 时使用)。"""

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
        # P1-C: 可观测性字段（非零时输出，避免日志膨胀）
        ti, to, lat = token_in_ctx.get(), token_out_ctx.get(), latency_ms_ctx.get()
        if ti:
            entry["token_in"] = ti
        if to:
            entry["token_out"] = to
        if lat:
            entry["latency_ms"] = lat
        return json.dumps(entry, ensure_ascii=False)


class _PrettyFormatter(logging.Formatter):
    """人类可读的彩色控制台格式。

    - 按 level 着色，WARNING/ERROR 一眼可辨
    - 省略空的 req/thread，避免启动日志噪声
    - logger 名只保留最后一段，缩短行宽
    - 时间只到秒 (HH:MM:SS)，开发期足够
    """

    _RESET = "\033[0m"
    _DIM = "\033[2m"
    _LEVEL_COLOR = {
        "DEBUG": "\033[90m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[41;97m",
    }

    def format(self, record):
        ts = self.formatTime(record, "%H:%M:%S")
        color = self._LEVEL_COLOR.get(record.levelname, "")
        level = f"{color}{record.levelname:<8}{self._RESET}"
        name = record.name.rsplit(".", 1)[-1]
        ctx = ""
        req, thread = request_id_ctx.get(), thread_id_ctx.get()
        if req or thread:
            ctx = f"{self._DIM} req={req} thread={thread}{self._RESET}"
        line = f"{ts} {level} {self._DIM}{name:<20}{self._RESET} {record.getMessage()}{ctx}"
        if record.exc_info and record.exc_info[1]:
            line += f"\n    {self._LEVEL_COLOR['ERROR']}⚠ {record.exc_info[1]}{self._RESET}"
        return line


# 第三方库噪声 logger —— 统一静音到 WARNING，避免污染控制台
_NOISY_LOGGERS = (
    "httpx", "httpcore", "neo4j", "jieba", "sentence_transformers",
    "transformers", "tokenizers", "urllib3", "asyncio",
)


def _silence_third_party():
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
    # jieba 额外用 print() 直接输出词典构建过程 → 关闭其 logger.debug 通道
    try:
        import jieba
        jieba.setLogLevel(logging.WARNING)
    except Exception:
        pass
    # 关闭 transformers/sentence_transformers 的 tqdm 进度条（须在导入前设置）
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")


def setup_logging(level: int = logging.INFO):
    """初始化日志（应用启动时调用一次）。

    - LOG_FORMAT=pretty (默认): 控制台彩色人类友好格式
    - LOG_FORMAT=json: 控制台输出结构化 JSON（供日志采集/管道）
    """
    fmt = os.getenv("LOG_FORMAT", "pretty").lower()
    console = logging.StreamHandler()
    console.setFormatter(_PrettyFormatter() if fmt == "pretty" else _FridgeJsonFormatter())

    logging.root.handlers = [console]
    logging.root.setLevel(level)
    _silence_third_party()
