# FridgeAI — 智能冰箱食材管理与菜谱推荐系统

基于 OneNET IoT 云平台 + LangChain/LangGraph AI Agent 的智能冰箱系统。RK3588 边缘节点上报食材数据，FastAPI 后端提供 323 道菜谱的 RAG 智能推荐，uni-app 前端支持流式 AI 对话。

## 架构概览

```
前端 (uni-app / Vue 3)
  │ WebSocket /ws/fridge (数据推送) + /ws/chat (AI 对话)
  ▼
后端 (FastAPI + LangChain v1 + LangGraph)
  │ HTTP API (iot-api.heclouds.com)
  ▼
OneNET IoT Cloud
  │ MQTT (mqtts.heclouds.com:1883)
  ▼
RK3588 边缘节点 — 冰箱传感器 + SQLite
```

## 核心特性

### AI Agent 对话

- **Subagents 多 Agent 协作**: 主 Agent 协调 3 个专业子 Agent（菜谱推荐/食材替换/烹饪知识）
- **5 层 Middleware**: ModelCallLimit → Summarization → HumanInTheLoop → ModelRetry → ToolRetry
- **Long-term Memory**: 用户偏好跨会话持久化（忌口/偏好菜系/人数）
- **流式输出**: `/ws/chat` token 级打字机效果 + 工具调用进度
- **Human-in-the-Loop**: 写操作需人工审批
- **Structured Output**: 菜谱推荐/食材替换返回结构化 JSON

### 食材管理与推荐

- **323 道菜谱**: RAG 混合检索（Neo4j 知识图谱 + Milvus HNSW 向量索引 + BM25）
- **倒排索引 + 模糊匹配**: 29 项食材别名 + 循环去前缀
- **智能推荐**: 基于冰箱库存自动推荐可制作菜谱，支持忌口过滤

### IoT 数据同步

- **HTTP 自适应轮询** (500ms→30s): 从 OneNET 拉取冰箱库存
- **上传队列**: 防抖 + 指数退避重试(3次) + 死信持久化
- **WebSocket 实时推送**: `/ws/fridge` 双向数据同步

## 技术栈

| 层级 | 技术 |
|------|------|
| **AI Agent** | LangChain v1 (`create_agent`, `@tool`, `Middleware`) |
| **状态管理** | LangGraph (`StateGraph`, `InMemorySaver`, `InMemoryStore`) |
| **后端框架** | FastAPI + WebSocket |
| **LLM** | DeepSeek v4 (flash / pro) |
| **向量数据库** | Milvus (HNSW, 512-dim) |
| **图数据库** | Neo4j (Recipe-Ingredient 知识图谱) |
| **前端** | uni-app (Vue 3) / HBuilderX |
| **IoT 平台** | OneNET Studio (China Mobile) |
| **异步 HTTP** | httpx (连接池) |

## 目录结构

```
FridgeApp/
├── Frontend/                       # uni-app 移动端
│   ├── pages/
│   │   ├── home/home.vue           # 冰箱主页 — 食材管理
│   │   ├── recipes/recipes.vue     # 智能食谱 — AI 推荐 + 对话
│   │   ├── add/add.vue             # 添加食材
│   │   └── settings/settings.vue   # 设置 — IP 配置
│   └── utils/
│       ├── store.js                # 响应式数据中心
│       ├── cloudSync.js            # OneNET WS 数据同步
│       ├── agentChat.js            # Agent 流式对话客户端
│       └── imageResolver.js        # 5 级图片回退
│
├── Backend/
│   ├── api/
│   │   ├── server.py               # FastAPI 入口 + lifespan
│   │   ├── dependencies.py         # 全局单例 (7 项)
│   │   ├── onenet_relay.py         # OneNET HTTP 轮询 + 上传队列
│   │   ├── ws_relay.py             # /ws/fridge 数据推送
│   │   ├── chat_relay.py           # /ws/chat Agent 流式对话
│   │   ├── tools.py                # 8 个 @tool + FridgeContext
│   │   ├── subagents.py            # 3 个专业子 Agent
│   │   ├── graph.py                # LangGraph StateGraph
│   │   ├── models.py               # Pydantic 数据模型
│   │   └── routes/                 # REST: recommend/search/detail/substitutions
│   ├── matching/                   # 倒排索引 + 模糊匹配
│   ├── rag_modules/                # Neo4j + Milvus + Hybrid RAG
│   ├── prompts/                    # ChatPromptTemplate 模板
│   ├── main.py                     # RAG系统 + Agent 工厂函数
│   └── config.py                   # GraphRAGConfig
│
└── docs/                           # 设计文档
    ├── LangChain_LangGraph_改进方案.md
    ├── LangChain_LangGraph_最新改进建议_2026-06-29.md
    └── Middleware体系改造方案.md
```

## 快速开始

### 环境要求

- Python 3.9+
- Neo4j (localhost:7687)
- Milvus (localhost:19530)
- DeepSeek API Key
- HBuilderX (前端)

### 后端启动

```bash
cd Backend
pip install -r requirements.txt

# 配置 .env（参考 .env.example）
# 必填: DEEPSEEK_API_KEY

uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
```

### 前端启动

HBuilder X 打开 `Frontend/` → 运行 → 内置浏览器 (H5)

手机端：设置页填入 PC 局域网 IP（4 段数字），确保同一 WiFi

## Agent 调用

```python
from api.dependencies import get_fridge_agent
from api.tools import FridgeContext

agent = get_fridge_agent()
result = agent.invoke(
    {"messages": [{"role": "user", "content": "能做什么菜?"}]},
    context=FridgeContext(
        current_inventory=[{"name":"鸡蛋","qty":6,"cal":74,"cat":"肉蛋生鲜类"}],
        user_preferences={"忌口":["花生"]},
        user_id="user_001",
    ),
)

# 多轮对话 (thread_id 继承历史)
from api.dependencies import get_fridge_graph
graph = get_fridge_graph()
config = {"configurable": {"thread_id": "user_001"}}
graph.invoke({"messages": [...]}, config=config)  # 第 2 轮继承上文
```

## WebSocket 协议

### /ws/fridge

| type | 方向 | 说明 |
|------|------|------|
| `food_update` | B→F | 全量食材推送 |
| `food_upload` | F→B | 前端上传 |
| `ack` | B→F | 上传已入队 |
| `upload_status` | B→F | 上传状态 |

### /ws/chat

| type | 方向 | 说明 |
|------|------|------|
| `chat` | F→B | 用户消息 |
| `stream_token` | B→F | LLM token（打字机） |
| `stream_tool_start` | B→F | 工具调用开始 |
| `stream_done` | B→F | 响应完成 |

## Agent 工具

| 工具 | 说明 |
|------|------|
| `get_fridge_inventory` | 读取冰箱食材清单 |
| `recommend_by_fridge` | 基于食材推荐菜谱(含忌口过滤) |
| `search_recipes_by_ingredients` | 显式食材搜索 |
| `get_recipe_detail` | 菜谱完整详情 |
| `find_substitutions` | 食材替换建议 |
| `search_cooking_knowledge` | RAG 烹饪知识问答 |
| `save_user_preferences` | 保存偏好到长期记忆 |
| `get_user_preferences` | 读取已保存的偏好 |

## Middleware 栈

```
1. ModelCallLimitMiddleware   单次最多 15 次模型调用
2. SummarizationMiddleware    超 4000 token 自动摘要压缩
3. HumanInTheLoopMiddleware   写操作需人工审批
4. ModelRetryMiddleware       LLM API 容错重试 (3次)
5. ToolRetryMiddleware        工具容错重试 (2次)
```

## 子 Agent

| 子 Agent | 底层工具 | 说明 |
|----------|---------|------|
| `recipe_expert` | recommend_by_fridge + search_recipes + get_detail | 菜谱推荐全流程 |
| `substitution_expert` | find_substitutions | 食材替换 (temperature=0.0) |
| `cooking_expert` | search_cooking_knowledge | 烹饪知识 RAG |

## 已知限制

- `InMemorySaver`/`InMemoryStore` 重启丢数据 → 生产需换 `PostgresSaver`/`PostgresStore`
- 无自动化测试
- 管道格式分隔符 `|` 和 `;` 与食材名冲突风险

## 许可证

MIT
