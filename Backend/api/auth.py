"""FastAPI API Key 认证依赖

所有 API 端点的认证层。通过 X-API-Key 请求头验证调用方身份。
当 API_KEY 环境变量未设置时(开发模式)，允许所有请求通过。
"""

import asyncio
import os
import logging

from fastapi import Security, HTTPException, status, WebSocket
from fastapi.security import APIKeyHeader

logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY", "")

if not API_KEY:
    logger.warning("API_KEY 未设置 — 所有 API 端点对外开放 (开发模式)")
else:
    logger.info("API_KEY 已配置 — API 认证已启用")

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)) -> bool:
    """验证 X-API-Key 请求头。开发模式下(API_KEY 未设置)允许所有请求。"""
    if not API_KEY:
        return True
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少 X-API-Key 请求头",
        )
    if api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无效的 API Key",
        )
    return True


def verify_ws_api_key(websocket: WebSocket) -> bool:
    """WebSocket 连接认证 — 从查询参数读取 api_key。

    开发模式(API_KEY 未设置)直接放行，保持零配置体验。
    生产模式: 缺失 api_key → close(4001), 无效 api_key → close(4003)。
    返回 True 表示验证通过，调用方继续 accept；返回 False 表示连接已关闭。

    必须在 websocket.accept() 之前调用，否则 close code 无法传递到客户端。
    """
    if not API_KEY:
        return True

    api_key = websocket.query_params.get("api_key", "")
    if not api_key:
        _ws_close(websocket, code=4001, reason="Missing api_key query parameter")
        return False
    if api_key != API_KEY:
        _ws_close(websocket, code=4003, reason="Invalid api_key")
        return False
    return True


def _ws_close(websocket: WebSocket, code: int, reason: str):
    """安全调度 WebSocket close —— 兼容有/无事件循环的上下文。"""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(websocket.close(code=code, reason=reason))
    except RuntimeError:
        # 无运行中的事件循环 (如测试环境) — 连接尚未 accept，无需真正 close
        pass
