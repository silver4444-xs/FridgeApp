"""
FastAPI 应用入口
启动: uvicorn api.server:app --host 0.0.0.0 --port 8000
"""
import os
import sys
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from api.auth import verify_api_key
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

from api.dependencies import recipe_db, inverted_index


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== FridgeAI 后端启动中 ===")

    # ── LangSmith 可观测性 ──
    # Phase 7: 零代码改动，仅读取环境变量即可开启全链路追踪
    # Agent 每次 LLM call / tool call 自动记录到 LangSmith
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        logger.info(f"[LangSmith] Tracing ENABLED — project={os.getenv('LANGSMITH_PROJECT', 'N/A')}")
    else:
        logger.info("[LangSmith] Tracing DISABLED — set LANGSMITH_TRACING=true to enable")

    # ── OneNET MQTT Relay + WebSocket 推送 ──
    _relay = None  # Fix #9: 提升作用域以便 shutdown 时清理
    try:
        from api.onenet_relay import OneNetRelay
        from api.ws_relay import broadcast

        _relay = OneNetRelay()

        async def _on_food_data(food_items):
            logger.info(f"[Relay->WS] Pushing {len(food_items)} items to clients")
            # 更新全局食材快照，供 Agent context 注入
            import api.dependencies as deps
            deps.current_fridge_inventory = food_items
            await broadcast({
                "type": "food_update",
                "foodItems": food_items,
                "isSnapshot": True,
            })

        _relay.on_data(_on_food_data)
        await _relay.connect()
        # 注册前端上传处理器
        from api.ws_relay import set_upload_handler, set_on_connect_handler
        set_upload_handler(_relay.upload_foods)
        set_on_connect_handler(_relay.push_current)
        logger.info("OneNET Relay 启动完成")
    except Exception as e:
        logger.warning(f"OneNET Relay 启动失败: {e}")

    # ── RAG 系统 ──
    try:
        from config import get_default_config
        from main import AdvancedGraphRAGSystem

        _rag = AdvancedGraphRAGSystem(get_default_config())
        _rag.initialize_system()
        _rag.build_knowledge_base()

        import api.dependencies as deps
        deps.rag_system = _rag
        logger.info("RAG 系统初始化完成")
    except Exception as e:
        logger.warning(f"RAG 系统初始化失败: {e}")

    # ── Phase 3.5 + Phase 4: 持久化 Store + Checkpointer ──
    # 使用 SQLite 替代 InMemory，数据在重启后保留
    # 共享同一 DB 文件: checkpoints.db
    import api.dependencies as deps

    # Store: 跨会话持久化用户偏好
    try:
        from api.persistent_store import SQLiteStore
        _db_path = os.getenv("SQLITE_DB_PATH", "checkpoints.db")
        deps.fridge_store = SQLiteStore(_db_path)
        logger.info("SQLiteStore 创建完成 (用户偏好持久化)")
    except Exception as e:
        logger.warning(f"SQLiteStore 创建失败，回退到 InMemoryStore: {e}")
        from langgraph.store.memory import InMemoryStore
        deps.fridge_store = InMemoryStore()

    # Checkpointer: HITL 中断状态持久化
    try:
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        _db_path = os.getenv("SQLITE_DB_PATH", "checkpoints.db")
        deps.fridge_checkpointer = AsyncSqliteSaver.from_conn_string(_db_path)
        await deps.fridge_checkpointer.setup()
        logger.info("AsyncSqliteSaver 创建完成 (HITL 状态持久化)")
    except Exception as e:
        logger.warning(f"AsyncSqliteSaver 创建失败，回退到 InMemorySaver: {e}")
        from langgraph.checkpoint.memory import InMemorySaver
        deps.fridge_checkpointer = InMemorySaver()

    # ── Phase 1: Agent 标准化 —— 创建 LangChain Agent ──
    # Phase 3.5: store + Phase 4: checkpointer
    try:
        import api.dependencies as deps
        if deps.rag_system:
            from main import create_fridge_agent_from_rag
            deps.fridge_agent = create_fridge_agent_from_rag(
                deps.rag_system,
                store=deps.fridge_store,
                checkpointer=deps.fridge_checkpointer,
                agent_mode="subagents")  # Phase 6: 启用多 Agent 协作
            logger.info("LangChain Agent 创建完成 (Phase 6: Subagents + Store + HITL)")
        else:
            logger.warning("RAG 系统未初始化，跳过 Agent 创建")
    except Exception as e:
        logger.warning(f"LangChain Agent 创建失败: {e}")

    # ── Phase 2: LangGraph 状态图 ──
    # Phase 3.5: store + Phase 4: checkpointer
    try:
        import api.dependencies as deps
        if deps.fridge_agent:
            from api.graph import create_fridge_graph
            deps.fridge_graph = create_fridge_graph(
                fridge_agent=deps.fridge_agent,
                store=deps.fridge_store,
                checkpointer=deps.fridge_checkpointer)
            logger.info("LangGraph StateGraph 创建完成 (Phase 2 + Store + HITL)")
        else:
            logger.warning("Agent 未创建，跳过 Graph 初始化")
    except Exception as e:
        logger.warning(f"LangGraph StateGraph 创建失败: {e}")

    # ── 菜谱数据库 ──
    try:
        import api.dependencies as deps
        from langchain_core.documents import Document
        if deps.rag_system and deps.rag_system.data_module:
            docs = deps.rag_system.data_module.documents
            if docs:
                adapted_docs = []
                for doc in docs:
                    adapted_docs.append(Document(
                        page_content=doc.page_content,
                        metadata={
                            "parent_id": doc.metadata.get("node_id", ""),
                            "dish_name": doc.metadata.get("recipe_name", "未知菜品"),
                            "category": doc.metadata.get("category", "其他"),
                            "difficulty": doc.metadata.get("difficulty", "未知"),
                            "source": doc.metadata.get("node_id", ""),
                        }
                    ))
                recipe_db.build_from_documents(adapted_docs)
                inverted_index.build(recipe_db.all())
                logger.info(f"菜谱数据库: {len(recipe_db)} 道, 倒排索引: {len(inverted_index)} 词条")
    except Exception as e:
        logger.error(f"菜谱数据库构建失败: {e}")

    logger.info("=== FridgeAI 后端就绪 ===")
    yield
    # Fix #9: shutdown 时清理 Relay (断开 OneNET 连接、取消轮询/上传 Worker)
    # 原有逻辑: _relay 为 try 块内局部变量，shutdown 时无法访问 → 资源泄漏
    # 修复后: _relay 提升到外层作用域，yield 后显式调用 disconnect()
    if _relay:
        try:
            await _relay.disconnect()
            logger.info("OneNET Relay 已断开")
        except Exception as e:
            logger.warning(f"OneNET Relay 断开失败: {e}")
    logger.info("=== FridgeAI 后端关闭 ===")


app = FastAPI(
    title="FridgeAI Recipe API",
    description="基于冰箱食材的智能菜谱推荐系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

from api.ws_relay import router as ws_router, ws_fridge
app.add_api_websocket_route("/ws/fridge", ws_fridge)

# WebSocket 路由不使用 Depends (认证在连接握手阶段处理)
app.include_router(ws_router)

# ── Phase 5: 流式输出 —— Agent Chat WebSocket ──
from api.chat_relay import router as chat_ws_router
app.include_router(chat_ws_router)

from api.routes.recommend import router as recommend_router
from api.routes.detail import router as detail_router
from api.routes.search import router as search_router
from api.routes.substitutions import router as substitutions_router
from api.routes.chat import router as chat_router

_auth = [Depends(verify_api_key)]
app.include_router(chat_router, prefix="/api", tags=["对话"], dependencies=_auth)
app.include_router(recommend_router, prefix="/api/recipes", tags=["推荐"], dependencies=_auth)
app.include_router(search_router, prefix="/api/recipes", tags=["搜索"], dependencies=_auth)
app.include_router(detail_router, prefix="/api/recipes", tags=["详情"], dependencies=_auth)
app.include_router(substitutions_router, prefix="/api/recipes", tags=["替换建议"], dependencies=_auth)


@app.get("/api/health-public")
def health_public():
    """公开健康检查端点 (无需 API Key, 供 Docker/负载均衡器使用)"""
    return {
        "status": "ok",
        "recipes_count": len(recipe_db),
        "index_size": len(inverted_index),
    }


@app.get("/api/health", dependencies=[Depends(verify_api_key)])
def health():
    return {
        "status": "ok",
        "recipes_count": len(recipe_db),
        "index_size": len(inverted_index),
    }
