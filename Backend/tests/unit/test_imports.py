"""
Import smoke test —— 验证 LangChain/LangGraph 1.x 迁移未破坏关键模块导入面。

无需 Neo4j / Milvus / DeepSeek，仅验证 import 完整（作为 manifest 变更的回归兜底）。
"""
import importlib

import pytest

# 关键模块：覆盖 Agent / Graph / 中间件 / 工具 / RAG 生成集成的 1.x API 面
_KEY_MODULES = [
    "api.graph",
    "api.middleware",
    "api.subagents",
    "api.tools",
    "api.chat_relay",
    "rag_modules.generation_integration",
    "main",
]


@pytest.mark.unit
@pytest.mark.parametrize("module_name", _KEY_MODULES)
def test_import_module(module_name: str) -> None:
    """每个关键模块都能在 1.x manifest 下成功导入"""
    mod = importlib.import_module(module_name)
    assert mod is not None


@pytest.mark.unit
def test_generation_module_uses_init_chat_model() -> None:
    """迁移后的生成集成模块应使用 init_chat_model（而非直接 ChatOpenAI 构造）"""
    import rag_modules.generation_integration as gen

    assert hasattr(gen, "GenerationIntegrationModule")
    assert gen.init_chat_model is not None
