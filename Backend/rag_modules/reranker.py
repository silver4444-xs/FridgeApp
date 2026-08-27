"""
Jina Reranker API 精排模块

对粗排候选文档调用 Jina Reranker API 进行逐对重打分，
零本地内存占用，免费额度 (100万 tokens/月) 覆盖日常使用。

环境变量:
    JINA_API_KEY: Jina API 密钥 (https://jina.ai/reranker)
    未配置时静默降级为粗排结果。
"""

import logging
import os
from typing import List

import requests
from langchain_core.documents import Document

logger = logging.getLogger(__name__)

JINA_RERANK_URL = "https://api.jina.ai/v1/rerank"
JINA_MODEL = "jina-reranker-v2-base-multilingual"


def _get_api_key() -> str:
    """读取 Jina API Key，未配置返回空字符串。"""
    return os.getenv("JINA_API_KEY", "").strip()


def rerank_with_jina(
    query: str,
    candidates: List[Document],
    top_k: int = 10,
    timeout: float = 10.0,
) -> List[Document]:
    """调用 Jina Reranker API 对候选文档精排。

    Args:
        query: 用户原始查询
        candidates: 粗排后的候选文档列表 (通常 top_k × 1.5)
        top_k: 精排后返回的文档数
        timeout: HTTP 请求超时秒数

    Returns:
        精排后的 Document 列表 (最多 top_k 个)。
        API 不可用时返回粗排结果的 top_k 截断。
    """
    if not candidates:
        return candidates

    api_key = _get_api_key()
    if not api_key:
        logger.info("JINA_API_KEY 未配置，跳过精排，使用粗排结果")
        return candidates[:top_k]

    documents_text = [doc.page_content for doc in candidates]

    try:
        response = requests.post(
            JINA_RERANK_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": JINA_MODEL,
                "query": query,
                "documents": documents_text,
                "top_n": top_k,
            },
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()

    except requests.exceptions.Timeout:
        logger.warning(f"Jina Reranker API 超时 ({timeout}s)，降级到粗排结果")
        return candidates[:top_k]
    except requests.exceptions.ConnectionError:
        logger.warning("Jina Reranker API 连接失败，降级到粗排结果")
        return candidates[:top_k]
    except Exception as e:
        logger.warning(f"Jina Reranker API 调用异常: {e}，降级到粗排结果")
        return candidates[:top_k]

    # 按 API 返回的 relevance_score 重排
    results = body.get("results", [])
    if not results:
        logger.warning("Jina Reranker 返回空结果，降级到粗排结果")
        return candidates[:top_k]

    ranked: List[Document] = []
    for item in results:
        idx = item.get("index", -1)
        if 0 <= idx < len(candidates):
            candidates[idx].metadata["rerank_score"] = item.get(
                "relevance_score", 0.0
            )
            candidates[idx].metadata["rerank_method"] = "jina"
            ranked.append(candidates[idx])

    logger.info(
        f"Jina Reranker 精排完成: {len(candidates)}候选 → {len(ranked)}结果"
    )
    return ranked[:top_k]
