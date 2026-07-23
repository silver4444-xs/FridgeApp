# FridgeAI P2 改进方案 — 工程实践与可扩展性

> 2026-07-23 | 源码级逐项分析，含文件路径、行号和改进方案

---

## 总览

| # | 问题 | 严重程度 | 改进周期 |
|---|------|---------|---------|
| P2-1 | 调用限流用简单计数器而非滑动窗口/令牌桶 | 运维风险 | 1 天 |
| P2-2 | 同义词覆盖缺少消融实验 | 论文缺口 | 2~3 天 |
| P2-3 | 无结构化日志 — 无 correlation ID、纯文本、上下文不传递 | 可调试性 | 2~3 天 |
| P2-4 | Milvus 每次启动强制重建（force_recreate=True 硬编码） | 启动性能 | 1 天 |
| P2-5 | 其他工程问题（Nginx SSL 注释、零前端测试、无 CI/CD、无 pyproject.toml、构建产物提交、fetch_images.py 缺失、LIMIT 1000 硬编码、nodeId 魔数无文档） | 工程标准化 | 持续 |

---

## P2-1: 调用限流用简单计数器

### 当前状态

**文件：** `Backend/main.py:697-700`

```python
ModelCallLimitMiddleware(
    run_limit=15,
    exit_behavior="end",
)
```

`ModelCallLimitMiddleware` 是 LangChain 库内置类（`langchain.agents.middleware`），内部维护整数计数器。达到 15 次后 `exit_behavior="end"` 直接停止 Agent 执行。

**四个问题：**

1. **简单计数器而非滑动窗口**：无法区分"1 秒内突发 15 次"（可能是死循环——工具调用→失败重试→再调用）和"5 分钟内正常使用 15 次"（合理的多步链式对话）

2. **阈值 15 是经验估算**：面试回答中坦言基于"简单对话 2-3 次、复杂 6-8 次、极端 10-12 次，留 3-5 次余量"。没有基于线上 P95/P99 数据验证，阈值不可通过环境变量配置

3. **硬停止（exit_behavior="end"）**：用户看到"已达调用上限"系统消息而非自然对话结束。三步链式调用（推荐→替换→烹饪技巧）可能在第二步被截断

4. **不跨请求累计**：每轮对话独立计数，恶意用户可通过不断发新消息绕过限制

### 改进方案

| 改动 | 位置 | 说明 | 工时 |
|------|------|------|------|
| 阈值可配置 | `main.py:698` | `run_limit=int(os.getenv("AGENT_MAX_CALLS", "15"))` | 5 分钟 |
| 线程级上限 | `main.py:697` | 追加 `thread_run_limit` 参数（LangChain 库如不支持则自行维护字典） | 0.5 天 |
| 自定义 TokenBucket | `api/middleware.py` 新建 | `TokenBucketMiddleware(max_tokens=15, refill_rate=3/min)` — 允许突发但限制长期速率 | 1 天 |

---

## P2-2: 同义词覆盖缺少消融实验

### 当前状态

三层同义词覆盖在三个文件中各自实现，无实验数据量化每层贡献：

| 层 | 文件 | 机制 |
|----|------|------|
| 第一层：索引构建时展开 | `inverted_index.py:19-33` | build 阶段食材同义词扩展→插入同义词索引键 |
| 第二层：搜索时展开 | `fuzzy_matcher.py:127-144` | normalize 中去修饰前缀→数量单位→同义词展开 |
| 第三层：子串兜底 | `inverted_index.py:39-54` | fuzzy_lookup 先精确查→再子串匹配 |

面试回答中给出了完整的实验设计（5 配置剥离对比，323 道菜谱的全部食材做查询集）但未执行。

### 改进方案

| 步骤 | 产出 | 工时 |
|------|------|------|
| 构建查询集 | `tests/rag/eval_data/synonym_ablation_queries.json` | 0.5 天 |
| 编写消融测试 | `tests/rag/test_synonym_ablation.py` — 逐层剥离，自动计算 Recall@5/10 | 1 天 |
| 运行实验+报告 | `docs/消融实验报告.md` | 0.5 天 |

---

## P2-3: 无结构化日志

### 当前状态

全项目 11+ 个模块使用完全相同的基础模式：

```python
# server.py:27, graph.py:22, tools.py:21, subagents.py:19
# chat_relay.py:16, onenet_relay.py:22, auth.py:13, ws_relay.py:15
# routes/recommend.py:13, 以及所有 rag_modules/*.py
logger = logging.getLogger(__name__)
logger.info(f"开始混合检索: {query}")
logger.warning(f"[Chat WS] Tool error: {error_tool} — {error_msg[:200]}")
```

**三个核心问题：**

1. **无 Correlation ID**：无法追踪"用户消息 → WS 接收 → Agent 推理 → 子 Agent → Neo4j 查询 → Milvus 检索 → 生成回复"完整链路。10 个用户同时使用时日志交织，无法按请求过滤

2. **纯文本格式**：无法被 ELK/Loki 等日志聚合系统解析。要统计超时率需正则解析文本而非按字段过滤

3. **上下文不传递**：`thread_id` 仅在 `chat_relay.py` 手动拼接。其他模块（tools、subagents、graph_rag_retrieval 等）完全不携带请求上下文

### 改进方案

**新增 `logging_config.py`：**

```python
import logging
from contextvars import ContextVar
from pythonjsonlogger import jsonlogger

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
thread_id_ctx: ContextVar[str] = ContextVar("thread_id", default="")

class FridgeJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["request_id"] = request_id_ctx.get()
        log_record["thread_id"] = thread_id_ctx.get()

def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(FridgeJsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    logging.root.handlers = [handler]
    logging.root.setLevel(logging.INFO)
```

**使用方式：**
```python
# chat_relay.py — 入口设置上下文
request_id_ctx.set(str(uuid.uuid4())[:8])
thread_id_ctx.set(thread_id)

# 所有其他模块 — 无需改动，ContextVar 自动传播
logger.info("开始混合检索")  # 自动携带 request_id + thread_id
```

输出示例（单行 JSON，可直接导入 Loki/ELK）：
```json
{"asctime": "2026-07-23T10:30:00", "name": "rag_modules.hybrid_retrieval",
 "levelname": "INFO", "message": "开始混合检索",
 "request_id": "a1b2c3d4", "thread_id": "user_abc"}
```

---

## P2-4: Milvus 每次启动强制重建

### 当前状态

`main.py:130-151` — `build_knowledge_base()` 已有加载/重建双路径：

```python
if self.index_module.has_collection():
    if self.index_module.load_collection():  # 尝试加载，成功则 return
        ...
        return
    # 加载失败 → 进入重建路径
```

但 `milvus_index_construction.py:227` 中 `force_recreate=True` 硬编码：

```python
def build_vector_index(self, chunks: List[Document]) -> bool:
    if not self.create_collection(force_recreate=True):  # ← 永远 True
        return False
```

一旦重建路径被触发，无论集合是否存在都会 `drop_collection` → `create_collection` → embedding 重新生成 → 800 条向量重新插入 → HNSW 重新构建（数分钟耗时）。

增量更新方法 `add_documents()`（L284-334）已实现但从未被调用。

### 改进方案

```python
# milvus_index_construction.py:227
force = force_recreate and self.client.has_collection(self.collection_name)
if not self.create_collection(force_recreate=force):
    return False
```

在 `main.py` 调用处：
- 首次启动：`build_vector_index(chunks, force_recreate=True)`
- 后续启动：优先 `load_collection()`，仅 schema 不兼容时重建
- 新增菜谱：调用 `add_documents(new_chunks)` 而非全量重建

---

## P2-5: 其他工程问题汇总

| # | 问题 | 位置 | 改进 |
|----|------|------|------|
| 5.1 | Nginx SSL 全被注释 | `deploy/nginx/conf.d/fridgeai.conf:54-98` | 取消注释 SSL server block；使用自签名证书（开发）或 Let's Encrypt（生产）；添加 HTTP→HTTPS 重定向 |
| 5.2 | 前端零测试 | `Frontend/` 无 `.test.*` / `.spec.*` 文件 | 引入 Vitest + @vue/test-utils + msw，优先覆盖 `agentChat.js`（WS 协议）和 `AgentChatBox.vue`（HITL 交互） |
| 5.3 | 无 CI/CD | 无 `.github/workflows/` | 添加 GitHub Actions：lint → unit test → integration test → build |
| 5.4 | 无 pyproject.toml | 项目根目录 | 创建 `pyproject.toml`，统一依赖管理与 pytest 配置 |
| 5.5 | 构建产物提交 | `Frontend/unpackage/dist/` | 追加到 `.gitignore` |
| 5.6 | fetch_images.py 缺失 | `deploy/scripts/fetch_images.py` 被引用但不存在 | 创建占位脚本或从部署脚本移除引用 |
| 5.7 | LIMIT 1000 硬编码无文档 | `graph_rag_retrieval.py:113`, `hybrid_retrieval.py:118` | 改为 Config 参数 + 注释说明用途（性能保护上限） |
| 5.8 | nodeId>=200000000 魔数无文档 | `graph_data_preparation.py:117,152,173`, `hybrid_retrieval.py:117` | 添加注释或改为可配置参数 |

---

## P2 改进优先级与时间估算

| 顺序 | 问题 | 工时 | 理由 |
|------|------|------|------|
| 1 | P2-3 结构化日志 | 2~3 天 | 影响所有模块可调试性，越早做收益越大 |
| 2 | P2-5.1 Nginx SSL | 0.5 天 | 安全基础 |
| 3 | P2-4 Milvus 不强制重建 | 1 天 | 启动速度从数分钟降至秒级 |
| 4 | P2-1 调用限流可配置 | 1 天 | 运维灵活性，小改动 |
| 5 | P2-5.3 CI/CD | 2 天 | 自动化质量保障 |
| 6 | P2-5.2 前端测试 | 3~5 天 | 覆盖核心交互路径 |
| 7 | P2-2 消融实验 | 2~3 天 | 论文加分 |
| 8 | P2-5.4~5.8 其他 | 持续 | 工程标准化 |

**P2 最小可行改进（1 周内）：**
P2-3 + P2-5.1 + P2-4 + P2-1 + P2-5.3 = 约 5~6 个工作日

---

> 所有代码引用基于 2026-07-23 源码版本，可在 `D:\Agent学习\FridgeApp\` 下验证。
