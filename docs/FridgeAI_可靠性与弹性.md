# FridgeAI 可靠性与弹性 — 降级矩阵 + 并发边界 + 多 worker Runbook

> 阶段 2「可靠性与弹性」实施文档（对应 `docs/FridgeAI_企业级LangGraph升级方案.md` 阶段 2）。
> 目标：把系统从「有中间件」升级为「可演示、可验证、可横向扩展」。

---

## 1. 降级矩阵

核心验收标准：**kill Neo4j / Milvus / DeepSeek 任一服务 → `/ws/chat` 仍返回可用结果或友好降级，不抛 500。**

| 依赖 | 触发条件 | 降级行为（代码位置） | 用户可见表现 | 恢复方式 |
|------|----------|----------------------|--------------|----------|
| **Milvus**（向量库） | 连接拒绝 / 查询超时 | `vector_search_enhanced()` 捕获异常返回 `[]`（`hybrid_retrieval.py:529-531`）；三路融合退化为 BM25 + 图索引两路 | 仍返回菜谱，语义相似度召回下降，偏关键词/图匹配 | 自动（每次查询重试连接，无需重启） |
| **Neo4j**（图库） | 连接失败 / 空子图 | ① `_neo4j_entity_level_search` / `_neo4j_topic_level_search` 返回 `[]`（`hybrid_retrieval.py:278-280, 431-433`）② `graph_rag_search` 返回空/占位 → `route_query` 回退 `hybrid_search_with_rerank`（`intelligent_query_router.py:238-245`） | 关系/搭配类复杂推理降级为传统混合检索，多跳推理质量下降 | 自动 |
| **Jina Reranker**（精排 API） | `JINA_API_KEY` 未配置 / 网络异常 / 超时 | `rerank_with_jina()` 静默返回粗排候选 top_k 截断（`reranker.py:52-54, 76-90`） | 结果顺序略差，仍返回结果 | 自动 |
| **DeepSeek**（LLM） | API 不可用 / 超时 / 鉴权失败 | ① Agent 路径错误边界返回友好错误（`api/graph.py:78-92`）② RAG 生成路径返回「抱歉，生成回答时出现错误…」（`generation_integration.py:83-85`）③ ModelRetry（3 次）+ CircuitBreaker（3 次失败熔断 30s） | 无法生成回答，返回友好提示（非堆栈、无敏感信息） | CircuitBreaker 30s 冷却后 HALF_OPEN 探测；DeepSeek 恢复后自动恢复 |
| **PostgreSQL**（持久化） | `POSTGRES_URI` 未配置 / 连接失败 | Store/Saver 回退 InMemory（`server.py:119-126, 151-158`） | 会话历史/用户偏好重启即失；多 worker 下 HITL 恢复可能跨 worker 失败 | 配置 `POSTGRES_URI` 后重启服务 |

> 说明：上表「用户可见表现」为运行时 kill 降级的验收结果。**启动时**降级见 §4 诚实边界。

---

## 2. 超时预算（总账）

`config.ReliabilityConfig` 集中管理超时，一处修改全局生效：

| 参数 | 默认值 | 环境变量覆盖 | 用途 |
|------|--------|--------------|------|
| `stream_total_timeout_seconds` | 60.0 | `STREAM_TOTAL_TIMEOUT` | `/ws/chat` 单轮流式总预算 |
| `stream_event_timeout_seconds` | 30.0 | `STREAM_EVENT_TIMEOUT` | 单个 `anext()` 事件超时 + HITL 自动 reject |
| `model_retry_max_delay` | 30.0 | —（`MiddlewareConfig`） | ModelRetry 指数退避上限 |
| `agent_http_read_timeout` | 60.0 | — | 主 Agent 模型 httpx read |
| `subagent_http_read_timeout` | 30.0 | — | 子 Agent 模型 httpx read |
| `generation_http_read_timeout` | 120.0 | — | RAG 生成流式 httpx read（需更长） |

**预算构成**：LLM 流式 60s 总预算 → 单事件 30s → ModelRetry max_delay 30s，三级联动防止级联超时。

---

## 3. 并发隔离边界

### 3.1 CircuitBreaker（进程内，单进程边界）

`CircuitBreakerMiddleware` 的状态机由 `threading.Lock()` 保护（`api/middleware.py:205`），**仅进程内线程安全**：

- ✅ **单实例 / `uvicorn` 单 worker**：边界正确，熔断状态全进程共享。
- ⚠️ **`uvicorn --workers N`**：每个 worker 独立进程，各自维护独立熔断状态。某工具在一个 worker 熔断后，其余 worker 仍继续调用该工具。
- ⚠️ **K8s / 多实例**：实例间熔断状态互不可见。

**结论**：单实例场景可接受。多实例需全局一致熔断时，须替换为分布式熔断器（Redis 计数器 + TTL），记录为已知边界，不阻塞当前阶段。

### 3.2 无状态化前提

多 worker 横向扩展的正确性依赖「状态外置」：

| 状态 | 外置方式 | 状态 |
|------|----------|------|
| 会话历史 / HITL 中断 | `AsyncPostgresSaver`（PG 连接池） | ✅ 跨 worker 恢复 |
| 用户长期偏好 | `AsyncPostgresStore`（PG 连接池） | ✅ 跨 worker 读取 |
| 菜谱库 / 倒排索引 | 启动时从 RAG 构建（每 worker 各自持有，只读） | ✅ 无状态冲突 |
| 冰箱食材快照 | OneNET Relay 回调 → `current_fridge_inventory`（进程内） | ⚠️ 每 worker 独立快照（Relay 单进程持有，不随 worker 复制） |
| CircuitBreaker 熔断态 | 进程内（见 3.1） | ⚠️ 每 worker 独立 |

---

## 4. 多 worker 验证 Runbook

### 4.1 前置条件

1. PostgreSQL 已启动，且 `.env` 中 `POSTGRES_URI` 已正确配置（否则回退 InMemory，跨 worker 恢复会失败）。
2. Neo4j / Milvus / DeepSeek 已启动（RAG 知识库源头是 Neo4j，缺一 Agent 不创建）。
3. Windows 须用 `--reload` 启动（`--reload` 强制 `SelectorEventLoop`，psycopg async 必需；无 `--reload` 时 uvicorn 用 `ProactorEventLoop` → AsyncPostgresStore/Saver 回退 InMemory）。

### 4.2 启动

```powershell
cd Backend
& "C:\Users\ASUS\.conda\envs\cook-rag-1\python.exe" -m uvicorn api.server:app --host 0.0.0.0 --port 8000 --workers 4 --reload
```

### 4.3 验证

```powershell
& "C:\Users\ASUS\.conda\envs\cook-rag-1\python.exe" scripts/verify_multi_worker.py
```

脚本对同一 `thread_id` 依次发多轮对话（含 HITL approve/reject 恢复），断言：

- 多轮上下文跨 worker 可恢复（PG checkpointer 生效）；
- HITL 中断 + resume 流程完整。

### 4.4 手动验收（kill 降级）

1. 起服务后，`/ws/chat` 发一条「推荐几个菜」确认 baseline。
2. kill Neo4j → 再发关系类问题（如「西红柿和鸡蛋怎么搭配」）→ 应回退 hybrid 并返回可用结果。
3. kill Milvus → 发关键词类问题 → 应 BM25 + 图索引兜底。
4. kill DeepSeek → 任意问题 → 应返回友好错误（非 500/堆栈）。
5. 依次恢复各服务 → 无需重启，功能自动恢复。

---

## 5. 诚实边界（本次明确不做）

| 边界 | 原因 |
|------|------|
| **启动时降级** | `main.py` 的 `initialize_system()` / `build_knowledge_base()` 在 Neo4j/Milvus 启动不可用时仍抛异常 → `server.py:79-91` 置 `rag_system=None` → 不建 Agent（全不可用）。RAG 知识库源头就是 Neo4j，启动时无图则无可降级数据（仅剩磁盘 pickle 缓存，风险高收益低）。阶段 2 验收标准是**运行时** kill 降级，故不改造启动路径。 |
| **分布式熔断（Redis）** | 单实例可接受，见 §3.1。 |
| **Langfuse 可观测性** | 属阶段 3，本次未实施。 |

---

## 6. 修改文件清单

| 文件 | 动作 |
|------|------|
| `Backend/config.py` | 新增 `ReliabilityConfig` + `reliability_config` 单例 |
| `Backend/api/server.py` | Store/Saver 连接池（`AsyncPostgresStore.from_conn_string(pool_config=…)` + 显式 `AsyncConnectionPool`） |
| `Backend/api/dependencies.py` | `POSTGRES_URI` 驱动开关注释对齐 |
| `Backend/rag_modules/neo4j_client.py` | driver 追加 3 个 pool kwargs |
| `Backend/api/middleware.py` | CircuitBreaker 并发边界 docstring |
| `Backend/api/chat_relay.py` | 超时读 `reliability_config`（60s/30s 魔法数字消除） |
| `Backend/main.py` / `api/subagents.py` / `rag_modules/generation_integration.py` | httpx 超时读 `reliability_config` |
| `tests/unit/test_reliability_config.py` | 新建：默认值 + 环境变量覆盖 + Neo4j kwargs 透传 |
| `tests/rag/test_degradation_matrix.py` | 新建：4 类故障注入降级测试 |
| `scripts/verify_multi_worker.py` | 新建：多 worker WS 验证脚本 |
| `Backend/main.py` / `rag_modules/generation_integration.py` | `print` → `logger`（启动/运行路径） |
