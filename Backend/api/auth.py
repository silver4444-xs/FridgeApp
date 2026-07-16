"""FastAPI API Key 认证依赖

所有 API 端点的认证层。通过 X-API-Key 请求头验证调用方身份。
当 API_KEY 环境变量未设置时(开发模式)，允许所有请求通过。
"""

import os
import logging

from fastapi import Security, HTTPException, status
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
