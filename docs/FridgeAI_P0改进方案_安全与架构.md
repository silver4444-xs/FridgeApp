# FridgeAI P0 改进方案 — 安全硬伤与架构欺骗

> 2026-07-23 | 源码级逐项分析，含文件路径、行号、当前代码片段和改进方案

---

## 总览

| # | 问题 | 严重程度 | 改进周期 |
|---|------|---------|---------|
| P0-1 | API 密钥暴露 + API_KEY 等于 LLM Key | 安全硬伤 | 1 天 |
| P0-2 | WebSocket 端点无鉴权 | 安全硬伤 | 1 天 |
| P0-3 | StateGraph 是单节点"假图" | 架构欺骗 | 2 天~2 周 |
| P0-4 | 图推理方法为硬编码字符串占位 | 最大架构欺骗 | 2 天~1 周 |
| P0-5 | 子 Agent 无隔离的全局单例 | 正确性硬伤 | 2~3 天 |
| P0-6 | InMemory 存储回退风险 + 单进程限制 | 可扩展性硬伤 | 3~5 天 |

---

## P0-1: API 密钥暴露

### 当前状态

**文件：** `Backend/.env`、`deploy/.env.production`、`Backend/.env.test`

经 git 验证：
- `git check-ignore` 确认文件已被 `.gitignore` 排除
- `git ls-files` 返回空 — 未被追踪
- `git log --all --full-history` 无历史 — 未提交过

**文件不在 Git 中，但存在于磁盘上，含真实密钥。**

| 文件 | 暴露内容 | 实时风险 |
|------|---------|---------|
| `Backend/.env` | DeepSeek API Key、LangSmith API Key（追踪已启用）、Pexels API Key、Neo4j 密码 | LangSmith 实时追踪所有开发对话（含用户冰箱数据） |
| `deploy/.env.production` | 同样的 DeepSeek/Pexels Key、Neo4j 密码 | `API_KEY` 与 `DEEPSEEK_API_KEY` 相同 — 拿到一个等于拿到全部 |
| `Backend/.env` L30 | `API_KEY=` 为空字符串 | 开发环境所有 REST API 免认证（`auth.py:27-28`） |

**核心风险链路：**

1. `.env` 文件未加密存储，本机任意进程均可读取 → 拿走 DeepSeek Key
2. LangSmith Tracing 在开发环境启用（`LANGSMITH_TRACING=true`）→ 所有对话（含用户冰箱数据）实时上传到 LangSmith 云端
3. `deploy/.env.production` 中 `API_KEY` 与 `DEEPSEEK_API_KEY` 相同 → API 鉴权形同虚设
4. Neo4j 密码 `all-in-rag` 明文存储 → 数据库直接暴露

### 改进方案

**第一步：密钥轮换（立即执行，无需改代码）**

1. DeepSeek 控制台 → 重新生成 API Key
2. LangSmith 控制台 → 重新生成 API Key
3. Pexels 控制台 → 重新生成 API Key
4. 新 Key 写入 `.env` 文件

**第二步：部署配置模板化**

- `deploy/.env.production` → 重命名为 `deploy/.env.template`，所有值替换为占位符
- 创建 `deploy/.env.example`（不含任何真实值）
- `.gitignore` 追加 `**/.env.production`

**第三步：开发环境安全加固**

- `Backend/.env` 中 `LANGSMITH_TRACING=false`（开发环境不需要全量追踪）
- `Backend/.env` 中 `API_KEY` 设为非空值（开发环境也应有基本鉴权）
- `auth.py:27-28` 改为本地请求免鉴权、非本地请求强制鉴权

**第四步：长期方案**

- 引入 `python-dotenv` + 环境变量注入
- 或使用系统级 Secret Manager（Windows Credential Manager / Vault）
- CI/CD 中通过 GitHub Secrets 注入，不在代码库中存储

---

## P0-2: WebSocket 端点无鉴权

### 当前状态

**文件：** `Backend/api/server.py:206-213`、`Backend/api/chat_relay.py:177-201`

REST API 和 WebSocket 的鉴权差异：

`server.py:221-222` — REST 路由有鉴权：
```python
_auth = [Depends(verify_api_key)]
app.include_router(chat_router, prefix="/api", tags=["对话"], dependencies=_auth)
```

`server.py:206-209` — WebSocket 路由无鉴权：
```python
app.add_api_websocket_route("/ws/fridge", ws_fridge)    # 无 _auth
app.include_router(ws_router)                             # 无 dependencies
```

`chat_relay.py:177-201` — 握手阶段无条件接受连接：
```python
@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()  # ← 无任何鉴权检查，直接接受
```

代码注释 `server.py:208` 声明"认证在连接握手阶段处理"，但握手阶段实际只调用了 `accept()`，未读取或验证任何请求头。

**攻击面量化：**

- `/ws/chat`：匿名用户可无限量发送消息，每次消息触发完整的 Agent 循环（1 次主 Agent + N 次子 Agent + 3~8 次工具调用），消耗 DeepSeek API 费用
- `/ws/fridge`：匿名用户可获取冰箱食材列表、通过上传接口推送伪造食材数据

### 改进方案

**核心思路：复用 `auth.py` 已有的 `API_KEY` 环境变量和验证逻辑，在 WebSocket 握手阶段验证请求头。**

`chat_relay.py` 修改：
```python
from api.auth import API_KEY

@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    # 握手前从请求头读取并验证 API Key
    api_key = websocket.headers.get("X-API-Key", "")
    if API_KEY and api_key != API_KEY:
        await websocket.close(code=4001, reason="Unauthorized")
        logger.warning(f"[Chat WS] 鉴权失败，连接被拒绝")
        return
    await websocket.accept()
    # ... 后续逻辑不变
```

`ws_relay.py` 的 `/ws/fridge` 同理。

**前端适配（uni-app 限制）：**

uni-app 的 `uni.connectSocket()` 不支持自定义请求头。替代方案 — URL 查询参数传 Key：
```javascript
const apiKey = getApp().globalState.apiKey || ''
const url = `${wsBase}/ws/chat?api_key=${encodeURIComponent(apiKey)}`
```
后端从 `websocket.query_params` 读取。

**额外加固（可选）：**

- 对单个 IP 的 WebSocket 连接数做限制（`chat_relay.py` 在 accept 前检查 IP 连接数）
- 对单连接的 Token 消耗做累计限制

---

## P0-3: StateGraph 是单节点"假图"

### 当前状态

**文件：** `Backend/api/graph.py:136-140`

图拓扑：
```python
workflow.add_node("recommend", recommend_node)
workflow.add_edge(START, "recommend")
workflow.add_edge("recommend", END)
```

`recommend_node` (`graph.py:59-85`) 的内容：
```python
async def recommend_node(state: FridgeAgentState, config) -> dict:
    inventory = state.get("current_inventory", [])
    if not inventory:
        import api.dependencies as deps
        inventory = deps.current_fridge_inventory
    user_id = config.get("configurable", {}).get("thread_id", "default")
    result = await fridge_agent.ainvoke(
        {"messages": state["messages"]},
        context=FridgeContext(
            current_inventory=inventory,
            user_id=user_id,
        ),
    )
    return {"messages": result["messages"]}
```

**图只是在 Agent 外面包了一层透明的壳。** 无条件路由、无分支、无子图、无并行执行。图的唯一作用是 LangGraph 自动在节点执行后做 checkpoint 持久化 — 但 checkpointer 也可以直接在 Agent 层注入。

`graph.py:154-232` 中的 78 行被注释的 Prompt Chaining 代码证明开发者清楚多节点架构应该是什么样子：
```
analyze_inventory → search_recipes → rank_results → generate_response
```
但这段代码从未被激活。

**面试问题：** 面试回答中描述"LangGraph 管图怎么走，中间件管 Agent 在一个节点里怎么跑"—这个分工的前提是多节点图。单节点下不存在"怎么走"的问题，checkpointer 只是每次 Agent invoke 后保存消息列表。这个描述与实际架构不符。

### 改进方案

**方案 A：移除假图（务实，2 天）**

将图彻底移除，所有调用点直接使用 Agent：
- `chat_relay.py:256` → `fridge_agent.ainvoke(Command(resume=...))`
- `routes/chat.py:21-41` → `fridge_agent.ainvoke()`

Agent 的 checkpointer 在 `create_agent()` 时注入，多轮对话能力不变。减少一层无意义的抽象。

**方案 B：激活 Prompt Chaining（论文加分，1~2 周）**

取消注释 `graph.py:154-232` 的四节点流水线，并加入条件路由：
```
START → analyze_inventory → search_recipes → rank_results → generate_response → END
                                    ↑                                              |
                                    └── 缺食材时 → substitution_lookup ─────────────┘
```

每个节点独立的 LLM 调用，LangSmith 上可观测四个阶段的各自耗时和成功率。
代价：每次推荐多 3 次 LLM 调用（约 1~2 秒额外延迟）。

**决策建议：** 面试/论文场景选 B（展示 LangGraph 编排能力），实际演示选 A（减少复杂度）。

---

## P0-4: 图推理方法是硬编码占位

### 当前状态

**文件：** `Backend/rag_modules/graph_rag_retrieval.py:597-607`

构成"图推理引擎"核心的三个方法：

```python
def _identify_reasoning_patterns(self, subgraph: KnowledgeSubgraph) -> List[str]:
    """识别推理模式"""
    return ["因果关系", "组成关系", "相似关系"]
    # ↑ 硬编码列表，完全不读取 subgraph 参数

def _build_reasoning_chain(self, pattern: str, subgraph: KnowledgeSubgraph) -> Optional[str]:
    """构建推理链"""
    return f"基于{pattern}的推理链"
    # ↑ 字符串模板，完全不使用 subgraph 的实际节点和边

def _validate_reasoning_chains(self, chains: List[str], query: str) -> List[str]:
    """验证推理链"""
    return chains[:3]
    # ↑ 只做切片截断，无任何验证逻辑
```

**无论传入什么查询和图子图，这三个方法永远返回相同或等效的输出。**

调用链路：
```
graph_rag_search()
  → _perform_multi_hop_reasoning()
    → _identify_reasoning_patterns(subgraph)   → ["因果关系", "组成关系", "相似关系"]
    → _build_reasoning_chain(pattern, subgraph) → "基于因果关系的推理链"
    → _validate_reasoning_chains(chains, query) → chains[:3]
```

整条"推理"链路不依赖任何输入数据。

**面试回答中**描述"多跳图推理—从'猪肉'出发 1 跳命中几十万道菜，2 跳展开步骤节点"时，这些"跳"确实发生在 Neo4j Cypher 查询 `MATCH (n)-[*1..5]-(m)` 中 — 这是 Cypher 的基础图遍历功能，不是"推理引擎"。真正应该做推理识别→推理链构建→推理链验证的三个方法，全部是占位实现。

### 改进方案

**方案 A：诚实标注（1 小时）**

将三个方法改为 `raise NotImplementedError`，在 `graph_rag_search` 中跳过推理环节，直接返回图遍历结果。降低 GraphRAG 路径的生成质量但消除欺骗。

```python
def _identify_reasoning_patterns(self, subgraph: KnowledgeSubgraph) -> List[str]:
    raise NotImplementedError("图推理引擎尚未实现，当前仅使用基础图遍历")
```

**方案 B：LLM 驱动推理链（推荐，2~3 天）**

用 LLM 真正实现：

1. `_identify_reasoning_patterns`：将 subgraph 的节点和边序列化为文本，让 LLM 判断涉及哪种推理类型（因果/组成/相似/替代/时序），返回分类

2. `_build_reasoning_chain`：让 LLM 基于 subgraph 中的实际路径（节点→边→节点），逐跳生成自然语言推理链。例如：
   ```
   番茄 → [REQUIRES] → 鸡蛋 → [RICH_IN] → 蛋白质
   → "番茄炒蛋需要鸡蛋，鸡蛋富含蛋白质，因此这道菜蛋白质含量较高"
   ```

3. `_validate_reasoning_chains`：让 LLM 逐条检查推理链中的每个断言是否基于 subgraph 中实际存在的边。对无法验证的断言标记为"推测"或丢弃。

技术细节：
- 使用与项目相同的 `deepseek-v4-flash` 模型，复用已有 `httpx.Client(timeout=...)`
- 将 subgraph 序列化为 `<节点ID>: <节点类型>(<属性>) --[<关系类型>]--> <节点ID>: <节点类型>(<属性>)` 格式
- 每次查询约多 1~2 次 LLM 调用（推理模式识别 + 推理链构建可合并为一次），额外延迟约 500ms~1s

**方案 C：GDS 算法驱动（学术价值最高，1 周+）**

安装 Neo4j Graph Data Science (GDS) 插件，使用以下算法替代 LLM：
- PageRank → 识别 subgraph 中的关键节点
- 节点相似度（Node Similarity）→ 量化实体间的关联强度
- 最短路径 + 路径聚合 → 生成推理链的图结构基础
- 社区检测（Louvain）→ 识别知识簇

不依赖 LLM 做推理，结果可复现、可解释。需要 GDS 插件安装（Docker Compose 中替换 Neo4j 镜像为包含 GDS 的版本）。

**推荐：方案 B。** 与项目已有技术栈一致，2~3 天可实现，产出可量化（推理链长度、验证通过率）。

---

## P0-5: 子 Agent 无隔离的全局单例

### 当前状态

**文件：** `Backend/api/subagents.py:112-145`

子 Agent 定义（三个全局单例）：
```python
_recipe_subagent = None         # 模块级全局变量
_substitution_subagent = None
_cooking_subagent = None

@tool("recipe_expert", ...)
def call_recipe_expert(query: str) -> str:
    global _recipe_subagent
    if _recipe_subagent is None:
        _recipe_subagent = _create_recipe_agent(
            _get_model(),                           # 共享同一模型实例
            [recommend_by_fridge, ...],
            store=fridge_store,                     # 全用户共享 store
            checkpointer=fridge_checkpointer,       # 全用户共享 checkpointer
        )
    result = _recipe_subagent.invoke({...})         # 同步调用，阻塞事件循环
```

**三个并发安全问题：**

1. **全用户共享实例**：用户 A 和 B 同时调用 `call_recipe_expert`，两个 `invoke()` 可能交叉执行。共同维护的 checkpointer 中混入两个人的对话历史。

2. **同步 `invoke()` 阻塞 async 事件循环**：子 Agent 执行 2~3 轮工具调用（每次 2~5 秒 LLM 延迟），期间事件循环无法处理其他连接的消息。

3. **子 Agent 看不到冰箱数据（关键缺陷）**：`call_recipe_expert(query: str)` 只接收字符串。子 Agent 内部的 `recommend_by_fridge` 工具依赖 `runtime.context.current_inventory`，但在子 Agent 的 context 中该字段为空列表。**这意味着子 Agent 实际推荐的不是用户冰箱里能做的菜。**

### 改进方案

**核心改动：从"复用全局单例"改为"每次请求创建，并透传 FridgeContext"。**

```python
@tool("recipe_expert", description="...")
def call_recipe_expert(query: str, runtime: ToolRuntime[FridgeContext]) -> str:
    """调用菜谱推荐子 Agent（每次请求创建独立实例）。"""
    from api.tools import (
        recommend_by_fridge,
        search_recipes_by_ingredients,
        get_recipe_detail,
    )

    # 每次创建独立 Agent，不共享状态
    agent = _create_recipe_agent(
        _get_model(),
        [recommend_by_fridge, search_recipes_by_ingredients, get_recipe_detail],
        # 不注入 store/checkpointer（子 Agent 应为无状态执行单元）
    )

    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": query}]},
            context=FridgeContext(
                current_inventory=runtime.context.current_inventory,  # ← 关键修复
                user_preferences=runtime.context.user_preferences,
                user_id=runtime.context.user_id,
            ),
        )
        return result["messages"][-1].content
    except Exception as e:
        logger.error(f"[recipe_expert] 调用失败: {e}")
        return f"菜谱专家暂时无法响应: {str(e)[:200]}"
```

**同步阻塞问题的缓解方案：**

- 短期：`asyncio.to_thread(agent.invoke, ...)` 为每个子 Agent 调用分配独立线程
- 长期：LangGraph 子图（`add_subgraph`）或将子 Agent 改为 `ainvoke()`（需确认 LangChain 版本支持）

**两个配套改动：**
- `call_substitution_expert` 和 `call_cooking_expert` 同理修改
- 删除 `subagents.py:112-114` 的三个全局变量

---

## P0-6: 存储不可用于生产

### 当前状态

**文件：** `Backend/api/server.py:88-114`、`Backend/api/dependencies.py:1-40`、`Backend/api/graph.py:127-128`

与最初评估不同，Store 和 Checkpointer **已有部分 SQLite 持久化**。

Lifespan（`server.py:88-114`）：
```python
# Store — 已用 SQLite
try:
    deps.fridge_store = SQLiteStore(_db_path)       # ← 首选
except:
    deps.fridge_store = InMemoryStore()             # ← 失败回退（静默）

# Checkpointer — 已用 SQLite
try:
    deps.fridge_checkpointer = AsyncSqliteSaver.from_conn_string(_db_path)  # ← 首选
except:
    deps.fridge_checkpointer = InMemorySaver()      # ← 失败回退（静默）
```

**仍存在的三个问题：**

**问题一：模块级全局单例（`dependencies.py:8-40`）**
```python
recipe_db: RecipeDatabase = RecipeDatabase()
fridge_agent = None      # ┐
fridge_graph = None      # │ 模块级变量
fridge_store = None      # │ 全局共享
fridge_checkpointer = None  # │
current_fridge_inventory: list = []  # ┘
```
单进程 FastAPI 无问题，但无法多 Worker 水平扩展。两个 Worker 各有独立的 `fridge_agent` 和 checkpointer 状态。

**问题二：`graph.py:127-128` 仍保留 InMemory 兜底**
```python
if checkpointer is None:
    checkpointer = InMemorySaver()  # ← 未注入时的默认值是内存
```
正常启动路径不会触发（lifespan 已注入 SQLite），但测试路径和手动创建 Graph 时可能走此分支。

**问题三：`current_fridge_inventory` 是纯内存列表**
```python
current_fridge_inventory: list = []  # ← 重启即丢失
```
每次服务重启后需等待 OneNET Relay 重新拉取食材数据。如果 OneNET 不可用，Agent 使用的冰箱数据为空。

### 改进方案

| 组件 | 当前 | 改进后 |
|------|------|--------|
| Store | SQLiteStore（单机可行） | 移除 InMemory 回退，初始化失败直接抛异常 |
| Checkpointer | AsyncSqliteSaver（单机可行） | 同上，fail-fast |
| 全局单例 | 模块级变量 | 挂载到 `app.state`（FastAPI 标准实践） |
| `current_fridge_inventory` | 纯内存列表 | 写入 Redis 或 SQLite，OneNET 更新→Agent 读取共用持久层 |
| 多进程扩展 | 不支持 | 引入 `RedisSaver`（LangGraph 内置支持）统一 checkpointer/store 后端 |

**短期（演示可用）：**

1. 移除 `server.py:100-102` 和 `server.py:112-114` 的 InMemory 回退分支，SQLite 初始化失败直接抛 `RuntimeError`
2. `graph.py:127-128` 的 `InMemorySaver()` 兜底改为抛出异常

**长期（生产可用）：**

1. 引入 Redis 作为统一后端 → LangGraph `RedisSaver` + `RedisStore`
2. 多 Worker 共享 Redis 连接（FastAPI + gunicorn/uvicorn `--workers N`）
3. 或使用 PostgresSaver + PostgresStore（与 SQLite 同模型，只是换后端）

---

## P0 改进优先级与时间估算

| 优先级 | 问题 | 方案 | 工期 |
|--------|------|------|------|
| 1 | P0-1 密钥暴露 | 密钥轮换 + 配置模板化 | 1 天 |
| 2 | P0-2 WS 无鉴权 | 握手阶段验证 API Key | 1 天 |
| 3 | P0-4 假图推理 | LLM 驱动推理链实现 | 2~3 天 |
| 4 | P0-5 子Agent单例 | 每次创建 + 透传Context | 2~3 天 |
| 5 | P0-3 单节点假图 | 移除假图或激活Prompt Chaining | 2 天~2 周 |
| 6 | P0-6 存储限制 | 移除InMemory回退 + Redis | 3~5 天 |

**最小可行改进（1 周内可完成）：**
P0-1 + P0-2 + P0-4 方案B + P0-5 + P0-6 短期方案 = 约 7 个工作日

---

> 所有代码引用均基于 2026-07-23 源码版本，可在 `D:\Agent学习\FridgeApp\Backend\` 下验证。
