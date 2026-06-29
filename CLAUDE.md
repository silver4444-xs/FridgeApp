# FridgeAI — 智能冰箱食材管理与菜谱推荐系统

> 最后更新: 2026-06-29 | 阶段: Phase 1-6 全部完成

## 项目概览

基于 OneNET IoT 云平台的智能冰箱系统。RK3588 边缘节点通过 MQTT 上报冰箱食材数据，Backend Relay HTTP 轮询 + WebSocket 推送给 uni-app 前端，FastAPI 后端提供 323 道菜谱智能推荐 + LangChain Agent 对话。

- **OneNET 产品**: `OAgTJW6fph`，主设备: `device_01` (RK3588)
- **启动**: `cd Backend && uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload`

## 目录结构 (关键文件)

```
FridgeApp/
├── Frontend/
│   ├── pages/ (home/recipes/add/settings/index)
│   ├── utils/ (store.js, cloudSync.js, mqttClient.js, imageResolver.js)
│   └── config/onenet.js
│
├── Backend/
│   ├── api/
│   │   ├── server.py           # FastAPI入口 + lifespan
│   │   ├── dependencies.py     # 全局单例 (8项)
│   │   ├── onenet_relay.py     # HTTP轮询 + 上传队列/重试/死信
│   │   ├── ws_relay.py         # /ws/fridge 数据推送
│   │   ├── chat_relay.py       # ★ /ws/chat Agent流式对话 (Phase 5)
│   │   ├── tools.py            # ★ 8个@tool + FridgeContext + 3套工具集
│   │   ├── subagents.py        # ★ 3个子Agent (Phase 6)
│   │   ├── graph.py            # ★ LangGraph StateGraph (Phase 2)
│   │   └── routes/             # REST: recommend/search/detail/substitutions
│   ├── matching/               # 倒排索引 + 模糊匹配 (323菜谱)
│   ├── rag_modules/            # Neo4j + Milvus + 图RAG
│   └── main.py                 # AdvancedGraphRAGSystem + create_fridge_agent() + create_fridge_graph_wrapper()
│
├── docs/ (改进方案/改进建议/Middleware改造方案)
└── CLAUDE.md
```

## lifespan 启动顺序

```
1. OneNet Relay
2. RAG 系统 (Neo4j + Milvus)
3. InMemoryStore (Long-term Memory)
4. InMemorySaver (HITL checkpointer)
5. Agent (create_agent: 6 tools + 5 middleware + store + checkpointer)
6. Graph (StateGraph: store + checkpointer)
7. RecipeDatabase (倒排索引)
```

## dependencies.py 全局单例

| 单例 | 类型 | Phase | 用途 |
|------|------|-------|------|
| `recipe_db` | RecipeDatabase | — | 323道菜谱 |
| `inverted_index` | InvertedIndex | — | 食材→菜谱索引 |
| `rag_system` | AdvancedGraphRAGSystem | — | Neo4j+Milvus RAG |
| `fridge_store` | InMemoryStore | 3.5 | 用户偏好跨会话持久化 |
| `fridge_checkpointer` | InMemorySaver | 4 | HITL 中断状态 |
| `fridge_agent` | create_agent() Runnable | 1 | Agent 单轮 |
| `fridge_graph` | CompiledStateGraph | 2 | 多轮对话+流式 |

## Agent 当前架构 (V3 Subagents 模式)

```
主 Agent (智能冰箱管家)
├── middleware (5层):
│   1. ModelCallLimitMiddleware   run_limit=15
│   2. SummarizationMiddleware    trigger=4000tokens
│   3. HumanInTheLoopMiddleware   save_user_preferences 需审批
│   4. ModelRetryMiddleware       3次/指数退避 1s→2s→4s
│   5. ToolRetryMiddleware        2次/仅 find_substitutions + search_cooking_knowledge
├── store: InMemoryStore
├── checkpointer: InMemorySaver
│
├── 直属 tools (3):
│   get_fridge_inventory     — ToolRuntime 读冰箱食材
│   save_user_preferences    — Store 持久化偏好
│   get_user_preferences     — Store 读取偏好
│
└── 子 Agent tools (3):
    recipe_expert ──────────→ [recommend_by_fridge, search, get_detail]
    substitution_expert ────→ [find_substitutions]  temperature=0.0
    cooking_expert ─────────→ [search_cooking_knowledge]
```

三种运行模式 (agent_mode 参数): "basic" (V1/4tool), "context" (V2/8tool), "subagents" (V3/6tool, 当前默认)

## 8 个基础 Tool (tools.py)

| Tool | Runtime 依赖 | 说明 |
|------|-------------|------|
| `get_fridge_inventory` | context | 冰箱食材清单 |
| `recommend_by_fridge` | context | 基于食材推荐菜谱(含忌口过滤) |
| `search_recipes_by_ingredients` | — | 显式食材搜索 |
| `get_recipe_detail` | — | 菜谱详情 |
| `find_substitutions` | — | 食材替换建议 |
| `search_cooking_knowledge` | — | RAG 烹饪问答 |
| `save_user_preferences` | context+store | 持久化偏好 → Long-term Memory |
| `get_user_preferences` | context+store | 读取历史偏好 |

## FridgeContext

```python
@dataclass
class FridgeContext:
    current_inventory: List[dict]    # 冰箱食材快照
    user_preferences: dict           # 单次调用 fallback
    user_id: str = "default"         # Store namespace 隔离
```

## 对话调用方式

```python
# Agent 直接调用
agent = get_fridge_agent()
result = agent.invoke(
    {"messages": [{"role": "user", "content": "能做什么菜?"}]},
    context=FridgeContext(current_inventory=[...], user_preferences={...}, user_id="u1"),
)

# Graph 多轮 (thread_id 继承历史)
graph = get_fridge_graph()
config = {"configurable": {"thread_id": "user_abc"}}
graph.invoke({"messages": [...]}, config=config)

# HITL 恢复
from langgraph.types import Command
graph.invoke(Command(resume={"decisions": [{"type": "approve"}]}), config=config)
```

## WS 消息协议

### /ws/fridge (数据推送)

food_update, food_upload, ack, upload_status, upload_failed, request_sync

### /ws/chat (Agent 对话) ★ Phase 5 新增

`chat` (F→B) → `stream_token`/`stream_tool_start`/`stream_tool_end`/`stream_done` (B→F)

## 数据流

```
RK3588 → MQTT → OneNET → Backend HTTP poll(500ms) → WS /ws/fridge → 前端
前端编辑 → WS upload → Backend入队 → HTTP set-device-property → OneNET → MQTT → RK3588
用户对话 → WS /ws/chat → graph.astream_events(v3) → 流式响应
```

## Long-term Memory (Store)

```
("preferences",) / user_id → {"忌口":["花生"], "偏好菜系":"川菜", "人数":2}
```

`InMemoryStore` (开发) → `PostgresStore` (生产，改一行 import)

## 已知限制

1. InMemorySaver/InMemoryStore 重启丢数据 → 生产换 PostgresSaver/PostgresStore
2. 无自动化测试
3. 管道格式分隔符冲突风险
4. DeepSeek tool-calling 兼容性待实测
5. 倒排索引 fuzzy_lookup O(n×m)
6. /ws/chat 端点已就绪，前端待适配
7. Subagents 首次调用冷启动延迟 (每次 new create_agent)

## 注意事项

- ⚠️ 禁止用 PowerShell `Set-Content` 编辑含中文的 .vue/.js (破坏 UTF-8)
- 后端启动前确认 `.env` 中 `DEEPSEEK_API_KEY`
- `agent_mode` 在 server.py lifespan 中设置，当前为 `"subagents"`
- httpx.Timeout 需4参数: connect/read/write/pool
