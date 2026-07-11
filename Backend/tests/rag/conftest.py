"""
ragas 0.4.3 与 langchain-community 0.4.2 兼容补丁 + RAG 系统 session fixture。

ragas/llms/base.py 无条件导入 VertexAI 模块, 但 langchain-community 0.4.2 已移除。
本项目不使用 VertexAI, 注入哑模块使 ragas 可正常导入。

Windows GBK 编码兼容: main.py 多处 print() 使用 emoji (✅❌❓⚠️),
在 Windows 控制台下触发 UnicodeEncodeError。强制 stdout 使用 UTF-8 编码。
"""
import sys
import io
from pathlib import Path

# 加载 .env.test 中的 EVAL_API_KEY 等环境变量
from dotenv import load_dotenv
_env_path = Path(__file__).resolve().parents[2] / ".env.test"
load_dotenv(_env_path)

# 强制 stdout 使用 UTF-8, 避免 main.py 中 emoji print() 在 Windows GBK 下崩溃
if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from unittest.mock import MagicMock


def _patch_vertexai():
    vertexai_chat = MagicMock()
    vertexai_chat.ChatVertexAI = type("ChatVertexAI", (), {})
    sys.modules["langchain_community.chat_models.vertexai"] = vertexai_chat
    vertexai_llm = MagicMock()
    vertexai_llm.VertexAI = type("VertexAI", (), {})
    sys.modules["langchain_community.llms.vertexai"] = vertexai_llm


_patch_vertexai()

# ── RAG 系统 session 级 fixture ──
# pytest 进程独立于 FastAPI server, 需自行初始化 rag_system 单例。
# 前置条件: Neo4j (7474/7687) + Milvus (19530) 需已启动。
# session scope 确保 3 个测试共享同一实例, 避免重复初始化。

import pytest
import api.dependencies as deps


@pytest.fixture(scope="session")
def init_rag_system():
    """
    初始化 RAG 系统并注入 api.dependencies.rag_system。

    流程与 server.py lifespan 一致:
    AdvancedGraphRAGSystem(DEFAULT_CONFIG)
    → initialize_system()    连接 Neo4j/Milvus/LLM, 创建检索引擎
    → build_knowledge_base() 已有 Milvus 集合则复用, 否则构建

    如已初始化则直接返回缓存实例。
    """
    if deps.rag_system is not None and deps.rag_system.system_ready:
        return deps.rag_system

    from config import DEFAULT_CONFIG
    from main import AdvancedGraphRAGSystem

    print("\n[RAG Fixture] 初始化 AdvancedGraphRAGSystem ...")
    _rag = AdvancedGraphRAGSystem(DEFAULT_CONFIG)

    print("[RAG Fixture] initialize_system() — 连接 Neo4j/Milvus/LLM ...")
    _rag.initialize_system()

    print("[RAG Fixture] build_knowledge_base() — 加载/构建知识库 ...")
    _rag.build_knowledge_base()

    deps.rag_system = _rag
    print(f"[RAG Fixture] 完成, system_ready={_rag.system_ready}")
    return _rag
