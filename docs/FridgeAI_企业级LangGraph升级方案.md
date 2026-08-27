# FridgeAI 企业级 LangGraph + LangChain 升级方案

> 版本：v1.0
> 日期：2026-08-21
> 状态：待评审 / 待实施
> 决策依据：目标=**面试/作品集展示**；框架=**升级到 1.x**；可观测性=**Langfuse 自托管**；优先级=**可靠性与弹性 + 可观测/评估/扩展**
>
> **相关文档**：本文是 [FridgeAI_企业级Agent对齐实施计划.md](FridgeAI_企业级Agent对齐实施计划.md) 与 [FridgeAI_企业级RAG对齐实施计划.md](FridgeAI_企业级RAG对齐实施计划.md)（2026-07-27 的 P0/P1/P2 差距分析路线图）的**下一步执行计划**——聚焦框架 0.3→1.x 迁移 + 可靠性/可观测两大已确认优先级，基于 2026-08-21 当前代码状态落地，而非重复差距分析。

---

## 目录

1. [背景与目标](#一背景与目标)
2. [现状评估](#二现状评估)
3. [目标架构](#三目标架构)
4. [总体路线图](#四总体路线图)
5. [分阶段详细方案](#五分阶段详细方案)
6. [LangChain 0.3 → 1.x 迁移专项](#六langchain-03--1x-迁移专项)
7. [Langfuse 可观测性专项](#七langfuse-可观测性专项)
8. [CI/CD 与测试专项](#八cicd-与测试专项)
9. [风险登记册](#九风险登记册)
10. [面试讲解脉络](#十面试讲解脉络)
11. [里程碑与交付物清单](#十一里程碑与交付物清单)

---

## 一、背景与目标

### 1.1 什么是本项目的「企业级」

对 FridgeAI 而言，「企业级」不是堆名词，而是可验证、可讲解、可演示的工程能力。结合已确认的优先级，落点为四个可度量的支柱：

| 支柱 | 含义 | 可度量标志 |
|------|------|-----------|
| **可靠性与弹性** | 外部依赖故障不拖垮主链路 | 熔断/重试/降级/持久化 checkpoint 端到端可演示 |
| **可观测与评估** | 每次推理可追踪、可复盘、可回归 | Langfuse 全链路 trace + 指标 + 离线评测闭环 |
| **扩展性** | 无状态化，多 worker 横向扩展 | checkpoint 落 PG 后任意加 worker 不丢会话 |
| **工程化** | 可复现构建、CI 门禁、可讲解决策 | pyproject + lockfile + CI 全绿 + ADR |

### 1.2 已确认的三项决策

1. **首要目标**：面试/作品集展示 —— 能讲透架构、能演示故障场景、文档可作证。
2. **框架版本**：升级到 LangChain 1.x + LangGraph 1.x（当前处于 0.3 → 1.x 中间态，见 §2.2）。
3. **可观测性**：Langfuse 自托管（开源、零成本、数据不出本机）。

### 1.3 范围边界（YAGNI）

以下**明确不做**，除非后续单独立项：

- Kubernetes / 云原生部署（本文档只给路径说明，不落地）。
- 多租户 SaaS 化（本项目是单实例智能冰箱，`thread_id` 已是隔离单元；RBAC 仅做 API Key + 轻量分级）。
- 收藏夹、周规划等业务功能（与「企业级」无关）。
- 付费 SaaS（LangSmith 付费版、托管 Postgres、托管 ClickHouse）。

---

## 二、现状评估

### 2.1 已经「比想象中更接近企业级」的部分

| 能力 | 现状 | 文件 |
|------|------|------|
| 7 层中间件栈 | CircuitBreaker / InputGuard / ModelCallLimit / Summarization / HITL / ModelRetry / ToolRetry | `api/middleware.py` |
| 结构化日志 | JSON 格式 + request_id/thread_id | `api/logging_config.py` |
| WS 鉴权 | `/ws/chat` `/ws/fridge` query 参数 API Key 校验 | `api/auth.py` |
| 持久化依赖 | 已装 `langgraph-checkpoint-postgres` `psycopg` `psycopg-pool` | `requirements.txt` |
| 容器化 | Dockerfile + compose + nginx + deploy.sh | `deploy/` |
| 离线评测 | Ragas + LangSmith 依赖 + 评测脚本 | `tests/rag/` |
| HITL | approve/reject 流式恢复 | `api/chat_relay.py` |

### 2.2 核心矛盾：版本处于「中间态」

- `requirements.txt` 锁定 `langchain==0.3.26`、`langgraph>=0.6.0`（**已过时**）。
- 实际运行环境已装 `langgraph==1.2.8`（记忆层迁移时已升级）。
- 代码已大量使用 **1.x API**：`langchain.agents.middleware`、`create_agent` 中间件、`langgraph.types.Command`。

**结论**：「升级到 1.x」的主要工作量是**让依赖清单诚实 + 修复已知破坏点**，而非从零重写。但正因为 manifest 与实际脱节，环境不可复现是当前最大风险。

### 2.3 未完成 / 技术债清单（本次必须收口）

| 项 | 严重度 | 说明 |
|----|--------|------|
| PostgreSQL 迁移未验证 | **P0** | 代码已改完（11 文件），但 PG 未起、后端未连真实 PG 重启验证过 |
| `Backend/agent(代码系ai生成)/` 孤儿目录 | P1 | 4 个 AI 生成残留文件，混入源码树 |
| `graph_rag_retrieval.py:597-607` 图推理硬编码占位 | P1 | 图 RAG 推理方法为占位，不真实 |
| `test_tools.py` 4 个既有失败（`KeyError 'status'`） | P1 | ToolResponse 统一格式留下的陈旧断言 |
| 无 `.github/workflows` | P2 | 无 CI/CD |
| 无 `pyproject.toml` | P2 | 依赖不可复现 |
| 前端零测试 | P2 | 本次仅补后端，前端测试列为 stretch |
| `docs/` 6 个文件残留 SQLite 旧引用 | P2 | 文档漂移 |

---

## 三、目标架构

### 3.1 架构图

```mermaid
flowchart TB
    subgraph Client["客户端 (uni-app H5/App)"]
        UI["AgentChatBox.vue<br/>WS /ws/chat"]
    end

    subgraph Edge["接入层"]
        NGINX["nginx (TLS 终止 / 反代)"]
    end

    subgraph App["FastAPI 应用 (可多 worker)"]
        API["api/server.py<br/>lifespan 组装单例"]
        AUTH["auth.py<br/>API Key 校验"]
        GRAPH["LangGraph StateGraph 1.x<br/>START→recommend→END"]
        AGENT["create_agent 1.x<br/>7 层中间件栈"]
        TOOLS["8 @tool + 3 子 Agent"]
        RELAY["chat_relay.py<br/>astream_events(v2) 流式"]
    end

    subgraph Obs["可观测层"]
        LOG["logging_config<br/>JSON + trace_id"]
        MET["Prometheus /metrics"]
        LF["Langfuse<br/>(自托管 tracing/eval)"]
    end

    subgraph Data["数据层"]
        PG["PostgreSQL<br/>AsyncPostgresSaver<br/>AsyncPostgresStore"]
        NEO["Neo4j (图 RAG)"]
        MIL["Milvus (向量)"]
        REDIS["Redis (可选, 阶段4)"]
    end

    LLM["DeepSeek<br/>(OpenAI 兼容)"]
    RERANK["Jina Reranker"]

    UI -->|WSS| NGINX -->|WSS| API
    API --> AUTH
    API --> GRAPH --> AGENT --> TOOLS
    RELAY --> GRAPH
    AGENT --> LLM
    AGENT -.tools.-> NEO & MIL & REDIS & RERANK
    GRAPH -->|checkpoint| PG
    TOOLS -->|store 偏好| PG
    API --> LOG & MET & LF
    LOG -.trace_id.-> LF
```

### 3.2 关键设计原则

1. **无状态化 worker**：会话历史与 HITL 中断全部落 `AsyncPostgresSaver`；用户偏好落 `AsyncPostgresStore`。应用进程本身零状态，`uvicorn --workers N` 即可横向扩展。
2. **中间件承担横切关注点**：重试/熔断/限流/摘要/HITL 全部在 `create_agent(middleware=[...])` 内，业务工具保持纯净。
3. **降级优先于崩溃**：Neo4j/Milvus/Jina/Langfuse 任一不可用，静默降级到可用路径，不阻断主问答链路。
4. **可观测是一等公民**：`trace_id` 贯穿「WS 请求 → LangGraph 节点 → 子 Agent → 工具 → LLM」，Langfuse 与结构化日志用同一 trace_id 关联。
5. **可复现构建**：`uv` + `pyproject.toml` + lockfile，CI 用同一 lockfile 安装。

---

## 四、总体路线图

六阶段增量推进，**每阶段可独立验证、独立 commit、可回滚**。依赖关系如下：

```mermaid
flowchart LR
    P0[阶段0 基线收口] --> P1[阶段1 框架1.x迁移+打包]
    P1 --> P2[阶段2 可靠性与弹性]
    P2 --> P3[阶段3 可观测与评估]
    P2 --> P4[阶段4 性能与扩展]
    P3 --> P5[阶段5 工程化+文档]
    P4 --> P5
```

> 阶段 2 与 3 是本次两大优先级；阶段 4 的 Redis/K8s 为可选，不阻塞主线。

---

## 五、分阶段详细方案

### 阶段 0 —— 基线收口（先止血）

**目标**：清掉烂尾与孤儿，锁定一个「诚实且可运行」的基线，为后续迁移提供干净起点。

**落地步骤**：

1. **验证 PostgreSQL 迁移**（承接记忆层迁移，按顺序）：
   ```bash
   # 1) 起 PG
   docker compose --env-file deploy/.env.production -f deploy/docker-compose.yml up -d postgres
   docker compose -f deploy/docker-compose.yml ps   # 确认 fridgeai-postgres healthy
   # 2) 起后端，Backend/.env 配 POSTGRES_URI
   cd Backend && uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload
   # 3) 确认日志无「回退到 InMemory」，出现 AsyncPostgresStore/Saver 创建完成
   ```
2. **验证三件事**（缺一不可）：
   - checkpointer：同 `thread_id` 两轮，第二轮能引用第一轮。
   - store：触发 `save_user_preferences`（HITL approve）→ 重启后端 → 能读回偏好。
   - HITL：approve 流式恢复 + reject 拒绝均通过（因工具已改 async，中断检测已修 `on_chain_stream`，需端到端回归）。
3. **清理孤儿目录**：删除 `Backend/agent(代码系ai生成)/`（4 个 AI 生成文件，先 `git log --oneline -- <path>` 确认无引用后删除）。
4. **修复 `test_tools.py` 4 个既有失败**（`KeyError 'status'` 陈旧断言，改为断言 `r["success"]`）。
5. **打基线 commit**：`chore: 基线收口 — PG迁移验证 + 清理孤儿目录 + 修复陈旧测试`。

**验收标准**：`/ws/chat` 多轮 + HITL + 偏好持久化在真实 PG 上端到端通过；`tests/agent/` + `tests/e2e/test_ws_chat.py` 全绿；`git status` 干净。

**风险**：PG 迁移若验证出问题，回查记忆层迁移的「关键 API 细节」逐项排查；最坏情况回退 InMemory（代码已有回退分支）。

---

### 阶段 1 —— 框架 1.x 迁移 + 依赖工程化

**目标**：让 manifest 诚实、可复现，代码全部对齐 LangChain 1.x / LangGraph 1.x。

**落地步骤**：

1. **引入 `pyproject.toml` + `uv`**：
   ```bash
   cd Backend
   uv init --no-workspace          # 生成 pyproject.toml
   uv add langchain langchain-core langchain-openai langgraph \
          langgraph-checkpoint-postgres psycopg[binary] psycopg-pool \
          fastapi "uvicorn[standard]" pydantic httpx neo4j pymilvus \
          numpy rank-bm25 sentence-transformers ragas langsmith python-dotenv
   uv lock                          # 生成 uv.lock 锁定 1.x 精确版本
   ```
   - conda 环境 `cook-rag-1` 保留为运行时，`uv` 负责依赖解析与 lockfile。
2. **冻结目标版本**（以 `uv lock` 当日最新稳定为准，参考值）：

   | 包 | 旧 | 新 |
   |----|----|----|
   | langchain | 0.3.26 | 1.x（~1.3） |
   | langchain-openai | 0.3.12 | 1.x |
   | langgraph | >=0.6.0 | 1.x（~1.2） |
   | langgraph-checkpoint-postgres | — | 3.x |
3. **逐文件迁移导入**（详见 §6）。
4. **修复已知 1.x 坑**（详见 §6.2，均已实测定位）。
5. **删除 `requirements.txt` 或改为 `uv export` 生成**：保留一份 `requirements.txt` 仅作 conda/pip 兜底，由 `uv export --format requirements-txt` 生成，避免手工漂移。

**关键代码迁移点**：
- `graph.py:20` `from langchain.agents import AgentState` → 确认 1.x 是否仍导出；否则改用 `TypedDict` + `Annotated[list[AnyMessage], add_messages]`。
- `main.py` `create_agent(...)` → 确认 1.x 签名（`tools` / `middleware` / `system_prompt` / `context_schema`）。
- 子 Agent `subagents.py` 的模型创建 → `ChatOpenAI` 1.x 参数（`base_url`、`extra_body`、`httpx.Client(timeout=...)`）。

**验收标准**：`uv run python -c "import api.server"` 通过；`uv run pytest` 全绿（含既有 4 个修复后的测试）；CI 有 import smoke test 兜底。

**风险与回滚**：1.x 破坏性改动集中在 `create_agent` / middleware / `ChatOpenAI` 参数。因有 lockfile，回滚 = `git checkout` + 旧 lockfile，安全。

---

### 阶段 2 —— 可靠性与弹性（优先级 1）

**目标**：把「可靠性与弹性」从「有中间件」升级为「可演示、可验证、可横向扩展」。

**落地步骤**：

1. **持久化收口**：`AsyncPostgresSaver` + `AsyncPostgresStore` 作为默认，`InMemory*` 仅 dev/test 回退。补齐 `dependencies.py` 注释与实际一致。
2. **连接池**：`psycopg-pool`（已引入）配合理上限；Neo4j 驱动用 `Neo4jClient` 共享单例（已有）；httpx 统一 `timeout`。
3. **并发隔离**：确认 `CircuitBreakerMiddleware` 的 `threading.Lock` 在多 worker 下行为 —— 单进程内隔离有效；跨 worker 熔断状态不共享，**记录为已知边界**（单实例可接受，K8s 时换 Redis 分布式熔断）。
4. **超时与背压**：`chat_relay.py` 60s 流式超时已有；补 LLM/tool 调用统一超时配置（`ModelRetryMiddleware` 已有 max_delay，补总超时预算）。
5. **优雅降级矩阵**（文档化 + 测试固化）：

   | 依赖 | 降级行为 | 现状 |
   |------|---------|------|
   | Neo4j | 跳过图 RAG，走 BM25/向量 | 部分 |
   | Milvus | 回退 BM25 纯文本 | 待验证 |
   | Jina Reranker | 保留粗排结果 | ✅ 已实现 |
   | DeepSeek | 友好错误消息（graph.py:78 错误边界） | ✅ 已实现 |
   | Langfuse | 关闭 tracing，不影响推理 | 待实现（阶段3） |
   | PostgreSQL | 回退 InMemory（仅 dev，生产告警） | 已实现 |

6. **多 worker 无状态化验证**：`uvicorn --workers 4` 启动，同一 `thread_id` 跨 worker 轮询仍能接续（checkpointer 落 PG 后天然成立）。

**验收标准**：故障注入测试通过 —— kill Neo4j/Milvus/DeepSeek 任一，`/ws/chat` 仍返回可用结果或友好降级；`--workers 4` 下多轮对话与 HITL 正常。

**风险**：分布式熔断是已知边界，不阻塞；若面试被追问，有清晰答案（「单实例用进程内锁，多实例换 Redis」）。

---

### 阶段 3 —— 可观测与评估（优先级 2）

**目标**：全链路可追踪 + 指标 + 离线评测闭环。

**落地步骤**：

1. **Langfuse 自托管（最小单机版）**：`deploy/docker-compose.yml` 增加 langfuse 服务（`langfuse/langfuse:3` + 单 postgres，不引入 clickhouse/redis）：
   ```yaml
   langfuse:
     image: langfuse/langfuse:3
     ports: ["127.0.0.1:3000:3000"]
     environment:
       - DATABASE_URL=postgresql://langfuse:${LANGFUSE_PASSWORD}@langfuse-db:5432/langfuse
       - NEXTAUTH_SECRET=${LANGFUSE_NEXTAUTH_SECRET}
       - SALT=${LANGFUSE_SALT}
       - ENCRYPTION_KEY=${LANGFUSE_ENCRYPTION_KEY}
     depends_on: [langfuse-db]
   ```
2. **接入 LangGraph**：LangChain/LangGraph 官方 Langfuse 集成（`langfuse` + callback handler 或 LangGraph trace），关键点：
   - `trace_id` 与 `logging_config.py` 的 `request_id/thread_id` 对齐。
   - 只追踪主问答链路，避免把健康检查/静态资源噪音打进去。
3. **Prometheus 指标**：`prometheus-fastapi-instrumentator` 挂 `/metrics`，暴露 QPS、延迟、错误率、工具调用耗时、熔断打开次数（`CircuitBreaker.describe()` 可导出为 gauge）。
4. **离线评测闭环**：
   - 用 Langfuse dataset（或现有 `tests/rag/eval_data/`）跑 RAGAS（忠实度/相关度/上下文召回）。
   - 阈值回归（沿用 0.50 阈值），CI 门禁：低于阈值阻止合并。
5. **降级**：`LANGFUSE_*` 未配置时静默关闭 tracing（与 Jina 降级同款模式）。

**验收标准**：一次 `/ws/chat` 请求在 Langfuse UI 可见完整 trace（WS → node → subagent → tool → LLM，含 token/耗时）；`/metrics` 可抓取；离线评测在 CI 跑通并产出报告。

---

### 阶段 4 —— 性能与扩展（可选增强）

**目标**：在不破坏前序稳定性的前提下，补性能与横向扩展路径。

**落地步骤**：

1. **全异步收尾**：盘点 `dependencies.py` 中 `get_*` 同步单例与 async 工具的混用点，统一为 async 生命周期（`AsyncExitStack`）。
2. **连接池补齐**：Neo4j `Neo4jClient` 连接池上限、Milvus 客户端复用、httpx `Client` 复用（避免每次子 Agent 新建连接）。
3. **Redis 缓存（可选）**：检索结果缓存（`search_cooking_knowledge` 热点查询）、session 元数据缓存。默认不引入，作为 stretch。
4. **K8s 路径（仅文档）**：输出 `docs/部署/K8s路径.md`，说明镜像、探针、多副本、PG 外部化、分布式熔断（Redis）的演进路径，不落地。

**验收标准**：压测对比（`--workers 1` vs `4`）吞吐提升；无内存泄漏（连接复用）。

---

### 阶段 5 —— 工程化 + 文档（面试交付）

**目标**：把能力固化为「可复现 + 可讲解 + 可作证」的交付物。

**落地步骤**：

1. **CI/CD**（`.github/workflows/ci.yml`，详见 §8）。
2. **测试四层补齐到 80%**：unit（工具/匹配/中间件）、integration（PG checkpointer/store）、e2e（WS 流式 + HITL）、eval（RAGAS）。
3. **ADR（架构决策记录）**：`docs/adr/` 下记录关键决策，每条含「背景/决策/后果」：
   - ADR-001 为什么选 LangGraph 而非手写 Agent loop
   - ADR-002 为什么 checkpoint 落 PostgreSQL 而非内存/Redis
   - ADR-003 为什么选 Langfuse 而非 LangSmith
   - ADR-004 为什么中间件化横切关注点
   - ADR-005 为什么 1.x 而非 0.3.x
4. **文档更新**：架构图、部署 runbook、`docs/` 6 个残留 SQLite 引用修正。

**验收标准**：CI 全绿；`uv run pytest` 覆盖率 ≥80%；`docs/adr/` 5 篇齐备；README 一页讲清架构。

---

## 六、LangChain 0.3 → 1.x 迁移专项

### 6.1 依赖对照

| 旧（0.3.x） | 新（1.x） | 迁移点 |
|------------|----------|--------|
| `langchain==0.3.26` | `langchain==1.x` | 主包整合，`create_agent` 为标准入口 |
| `langchain-openai==0.3.12` | `langchain-openai==1.x` | `ChatOpenAI` 参数变化 |
| `langgraph>=0.6.0` | `langgraph==1.x` | checkpoint/store/事件 API 变化 |
| `langchain.agents.AgentState` | 自定义 `TypedDict` 或 `AgentState` | 见 6.2 |

### 6.2 已实测定位的坑（直接采纳，避免重踩）

> 来源：本项目 2026-07~08 会话实测，非猜测。

1. **`extra_body` 失效**：DeepSeek 需通过 OpenAI 兼容端点透传额外参数（如 `n`、`stop`）。langchain-openai 1.x 下 `extra_body` 传递路径变化，需用 `ChatOpenAI(..., extra_body={...})` 且确认异步路径生效；必要时用 `httpx.Client` 自定义 transport。
2. **`astream_events(v3)` 非 async iterator**：必须用 **v2 + 内置 `anext()`**，否则流式静默。
3. **`on_chain_interrupt` 不是有效事件名**：HITL 中断以 `on_chain_stream` 事件携带 `chunk = {'__interrupt__': (Interrupt(...),)}` 出现。`include_types` 若含 `on_chain_interrupt` 会产出 **0 个事件**。已改为 `on_chain_stream` + `_is_interrupt_chunk()`。
4. **`AsyncPostgresSaver.from_conn_string()` / `AsyncPostgresStore.from_conn_string()` 返回 async context manager**，不是对象本身：必须 `await AsyncExitStack.enter_async_context(...)` 再 `await .setup()`。
5. **async `@tool`**：`.func = None`，协程存在 `.coroutine`。测试/直接调用用 `tool.coroutine(...)`，不是 `tool.func(...)`。
6. **子 Agent 模型必须带 `httpx.Client(timeout=...)`**：否则 DeepSeek 无超时挂起。

### 6.3 迁移顺序建议

1. 先迁 `main.py` 的 `create_agent` + 中间件（最高风险，其余依赖它）。
2. 再迁 `api/graph.py`（状态定义 + StateGraph）。
3. 再迁 `api/subagents.py`（子 Agent 模型创建）。
4. 再迁 `api/chat_relay.py`（事件流 + HITL）。
5. 最后迁 `api/tools.py`（async `@tool` 收尾）。
6. 每步 `uv run pytest` 回归。

---

## 七、Langfuse 可观测性专项

### 7.1 集成方式

推荐 **LangGraph + Langfuse 官方集成**：用 `langfuse` 的 LangGraph/LangChain 回调，在 `graph.astream_events` 处注入 trace handler，使每个 node/subagent/tool/LLM 调用自动成 span。

### 7.2 trace_id 贯穿方案

```
HTTP/WS 请求 → logging_config 生成 request_id + thread_id
             → 作为 Langfuse trace 的 metadata / user_id
             → 日志与 trace 用同一 thread_id 关联
```

排查一条流式回复：先用 thread_id 在日志里定位，再在 Langfuse 里看 token/耗时/工具链。

### 7.3 降级与成本

- 未配置 `LANGFUSE_HOST` → tracing 关闭，零开销。
- 本地采样：生产可按比例采样（`sample_rate`），避免打爆自托管库。

---

## 八、CI/CD 与测试专项

### 8.1 GitHub Actions 流水线（`ci.yml`）

```yaml
name: ci
on: [push, pull_request]
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --locked
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run mypy api matching rag_modules --ignore-missing-imports
  test:
    needs: lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_USER: fridge, POSTGRES_PASSWORD: test, POSTGRES_DB: fridge }
        ports: ["5432:5432"]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --locked
      - run: uv run pytest -m "not eval" -q
      - run: uv run pytest -m eval -q
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
  docker:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f deploy/Dockerfile.backend .
```

### 8.2 测试分层与覆盖率目标

| 层 | 目录 | 目标 |
|----|------|------|
| unit | `tests/unit/` | 工具/匹配/中间件，≥80% |
| integration | `tests/integration/` | PG checkpointer/store（真实 PG） |
| e2e | `tests/e2e/` | WS 流式 + HITL |
| eval | `tests/rag/` + `tests/agent/` | RAGAS / DeepEval，阈值门禁 |

---

## 九、风险登记册

| # | 风险 | 概率 | 影响 | 缓解 |
|---|------|------|------|------|
| R1 | 1.x 迁移破坏 `create_agent`/中间件 | 中 | 高 | lockfile 可回滚；分 5 步迁移，每步回归 |
| R2 | PG 迁移验证不过 | 低 | 中 | 代码已有 InMemory 回退；回查 memory 关键 API 细节 |
| R3 | DeepSeek 参数透传（extra_body）反复 | 中 | 中 | 已实测定位；httpx 自定义 transport 兜底 |
| R4 | Langfuse 自托管拖慢推理 | 低 | 中 | 采样 + 关闭开关 + 降级 |
| R5 | 多 worker 熔断状态不共享 | 中 | 低 | 单实例可接受；K8s 时换 Redis（文档化） |
| R6 | 前端零测试拖后腿 | 高 | 低 | 后端为主；前端测试列 stretch |
| R7 | 图推理硬编码占位（已知限制） | — | 中 | 诚实标注；不属本次「企业级」核心，列为后续 |

---

## 十、面试讲解脉络

> 目标 = 面试/作品集。文档是「证物」，以下脉络是「话术」。每个节点都能落到本项目的一个可演示点。

1. **架构一句话**：「FastAPI + LangGraph 1.x 的多智能体冰箱助手，会话与长期记忆持久化到 PostgreSQL，7 层中间件做可靠性，Langfuse 做全链路观测，离线评测闭环做回归。」
2. **为什么用 LangGraph 而非手写 loop** → ADR-001：状态图显式化、checkpoint 免费获得、HITL 原生中断恢复、可流式。
3. **为什么 checkpoint 落 PostgreSQL** → ADR-002：多 worker 无状态化、崩溃恢复、`thread_id` 天然多用户隔离。
4. **可靠性怎么保证** → 演示 CircuitBreaker（kill Neo4j 看熔断）、ModelRetry（jitter 退避）、InputGuard（注入词拦截）、Summarization（长对话压缩）。
5. **可观测怎么落地** → 打开 Langfuse，一条 trace 讲完「WS → 节点 → 子 Agent → 工具 → LLM」的 token 与耗时。
6. **怎么证明质量** → 离线评测（RAGAS 忠实度/相关度）+ CI eval 门禁 + 80% 覆盖。
7. **诚实边界** → 主动讲：图推理当前是硬编码占位（R7）、分布式熔断未做（R5）、前端无测试（R6）。**「我知道边界在哪」比「假装完美」更企业级。**

---

## 十一、里程碑与交付物清单

| 里程碑 | 交付物 | 完成标志 |
|--------|--------|---------|
| M0 基线 | 干净 commit + PG 验证 | `/ws/chat` 多轮+HITL 在 PG 上过 |
| M1 框架 | `pyproject.toml` + `uv.lock` | `uv run pytest` 全绿 |
| M2 弹性 | 降级矩阵测试 | 故障注入通过 + `--workers 4` 过 |
| M3 观测 | Langfuse + /metrics + eval CI | 一条 trace 完整可看 |
| M4 扩展 | 连接池 + K8s 文档 | 压测提升 |
| M5 交付 | CI 全绿 + ADR×5 + runbook | README 一页讲清 |

---

## 附：立即可以开始的 3 件事

1. **起 PG 验证迁移**（阶段 0 第一步，命令见 §阶段0），把「代码已改完未验证」的烂尾闭环。
2. **`uv init` + `uv add` + `uv lock`**（阶段 1 第一步），让依赖清单变诚实。
3. **删孤儿目录 + 修 4 个陈旧测试**（阶段 0），给基线一个干净起点。

这三件事互不依赖，可并行，且都不涉及风险最高的 `create_agent` 迁移，是低风险高收益的破冰动作。
