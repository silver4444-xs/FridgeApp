"""
Agent 测试 conftest — 初始化菜谱数据库 + fridge_agent 单例

在测试中绕过 FastAPI lifespan，直接:
  1. 从 Backend/data/dishes/*.md 加载菜谱文档，构建 recipe_db + inverted_index
     （不依赖 Neo4j/Milvus，复用 IngredientExtractor 解析 HowToCook Markdown 格式）
  2. 调用 main.create_fridge_agent() 创建 Agent（agent_mode="subagents"）
  3. 注入到 api.dependencies
"""
import os
import sys
import pytest
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv()

DISHES_DIR = BACKEND_DIR / "data" / "dishes"

# 顶层目录名 → 中文分类 (HowToCook 目录约定)
_CATEGORY_MAP = {
    "aquatic": "水产",
    "breakfast": "早餐",
    "condiment": "调料",
    "dessert": "甜点",
    "drink": "饮品",
    "meat_dish": "肉菜",
    "semi-finished": "半成品",
    "soup": "汤羹",
    "staple": "主食",
    "vegetable_dish": "素菜",
}


def _load_recipe_documents():
    """从 Backend/data/dishes/*.md 加载菜谱文档（等价于 server lifespan 的文档构建）。

    每个 Markdown 文件格式:
        # {菜名}的做法
        描述 / 预估烹饪难度：★★★★
        ## 必备原料和工具 / ## 操作 / ## 附加内容

    Returns:
        List[Document]，metadata 含 parent_id/dish_name/category/difficulty/source。
    """
    from langchain_core.documents import Document

    documents = []
    if not DISHES_DIR.is_dir():
        return documents

    for md_path in sorted(DISHES_DIR.rglob("*.md")):
        # 跳过 template 目录下的示例菜
        if "template" in md_path.parts:
            continue

        try:
            content = md_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # 菜名: 首行 "# {name}的做法"
        dish_name = "未知菜品"
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#"):
                dish_name = line.lstrip("#").strip().removesuffix("的做法").strip()
                break

        # 难度: "预估烹饪难度：★★★★" → 星数
        difficulty = "未知"
        for line in content.splitlines():
            if "预估烹饪难度" in line:
                stars = line.count("★")
                if stars:
                    difficulty = str(stars)
                break

        # 分类: 顶层目录名
        rel = md_path.relative_to(DISHES_DIR)
        top_dir = rel.parts[0] if len(rel.parts) > 1 else ""
        category = _CATEGORY_MAP.get(top_dir, "其他")

        documents.append(Document(
            page_content=content,
            metadata={
                "parent_id": rel.with_suffix("").as_posix(),
                "dish_name": dish_name,
                "category": category,
                "difficulty": difficulty,
                "source": str(md_path),
            },
        ))

    return documents


@pytest.fixture(scope="session", autouse=True)
def init_recipe_db():
    """session 级别: 用 Markdown 构建 recipe_db + inverted_index 单例。"""
    import api.dependencies as deps

    if len(deps.recipe_db) == 0:
        docs = _load_recipe_documents()
        deps.recipe_db.build_from_documents(docs)
        deps.inverted_index.build(deps.recipe_db.all())

    return deps.recipe_db


@pytest.fixture(scope="session", autouse=True)
def init_agent(init_recipe_db):
    """session 级别: 初始化 fridge_agent 单例，所有 agent 测试共享。

    依赖 init_recipe_db，确保 Agent 工具调用时菜谱数据库已就绪。
    """
    import api.dependencies as deps

    if deps.fridge_agent is not None:
        return deps.fridge_agent

    if not os.getenv("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY not set — cannot initialize Agent")

    from main import create_fridge_agent
    from langgraph.store.memory import InMemoryStore
    from langgraph.checkpoint.memory import InMemorySaver

    store = InMemoryStore()
    checkpointer = InMemorySaver()

    agent = create_fridge_agent(
        model_name=os.getenv("LLM_MODEL", "deepseek-v4-flash"),
        temperature=0.0,
        max_tokens=2048,
        store=store,
        checkpointer=checkpointer,
        agent_mode="subagents",
        enable_hitl=False,
    )

    deps.fridge_agent = agent
    deps.fridge_store = store
    deps.fridge_checkpointer = checkpointer

    return agent


@pytest.fixture(scope="module")
def agent_graph():
    """创建带 InMemoryStore + InMemorySaver 的 StateGraph，支持多轮对话测试。"""
    import os
    from langgraph.store.memory import InMemoryStore
    from langgraph.checkpoint.memory import InMemorySaver

    os.environ.setdefault("DEEPSEEK_API_KEY", os.getenv("DEEPSEEK_API_KEY", ""))
    from main import create_fridge_graph_wrapper
    return create_fridge_graph_wrapper(store=InMemoryStore(), checkpointer=InMemorySaver())
