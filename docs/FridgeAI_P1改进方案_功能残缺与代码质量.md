# FridgeAI P1 改进方案 — 功能残缺与代码质量

> 2026-07-23 | 源码级逐项分析，含文件路径、行号、当前代码和改进方案

---

## 总览

| # | 问题 | 严重程度 | 改进周期 |
|---|------|---------|---------|
| P1-1 | HITL 人机审批严重不完整 | 功能残缺 | 5~7 天 |
| P1-2 | 工具返回结构不一致 | 代码质量 | 2~3 天 |
| P1-3 | Combined 路由退化为 Round-robin 盲插 | 检索质量 | 1~4 天 |
| P1-4 | Neo4j 无同义关系边 + 三个独立驱动实例 | 架构缺陷 | 3 天 |
| P1-5 | 三种检索分数不可通约的加权融合 + BM25 未调优 | 数学缺陷 | 2 天 |
| P1-6 | 测试标准过低 | 质量保障 | 持续 |
| P1-7 | find_substitutions 使用独立模型实例 | 正确性风险 | 1 天 |
| P1-8 | Neo4j 使用 CONTAINS 而非全文索引 | 性能隐患 | 1 天 |
| P1-9 | cooking_knowledge 浮升因子 1.4 任意硬编码 | 启发式缺陷 | 1 天 |

---

## P1-1: HITL（人机审批）严重不完整

### 当前状态

HITL 涉及三个文件、四条路径，但每条都有缺口。

**触发端 — `main.py:711-728`：**

```python
HumanInTheLoopMiddleware(
    interrupt_on={"save_user_preferences": ...},  # ← 仅 1 个工具
)
# 注释掉的拦截点：clear_inventory, delete_favorite_recipes 均未实现
```

仅 `save_user_preferences` 一个工具触发审批。其他写操作（清空冰箱、删除收藏）不设防。

**流式恢复 — `chat_relay.py:248-268`：**

```python
elif msg_type == "resume":
    thread_id = data.get("thread_id", "default")
    decision = data.get("decision", "approve")
    result = await fridge_graph.ainvoke(
        Command(resume={"decisions": [{"type": decision}]}),
        config=config,
    )
    await websocket.send_json({
        "type": "stream_done",
        "reply": result["messages"][-1].content,  # ← 一次性返回全文，不走流式 token
    })
```

三个缺陷：
1. **不流式** — 审批恢复后整个回复一次性 `stream_done`，前端无打字机效果，与正常对话体验割裂
2. **不处理 reject** — `decision` 可以是 "reject" 但代码不做分支，直接传给 Command 而不区分行为
3. **无超时清理** — 用户离开后中断永久占据 checkpointer 空间，无后台清理机制

**断线场景 — 无重连支持：**

WebSocket 断开后，如果 checkpointer 中存在待审批的中断，用户重新连接时看不到未处理的审批请求。`chat_relay.py:201` 的 `websocket.accept()` 后没有查询 `thread_id` 是否有待处理中断的逻辑。

**REST 路径 — `routes/chat.py:21-41`：**

```python
@router.post("/chat")
async def chat(req: ChatRequest):
    result = await graph.ainvoke(...)  # ← 若触发 HITL 中断，永远等不到 resume
```

REST `/api/chat` 无 `/api/chat/resume` 端点，触发 HITL 时直接挂起。

### 改进方案

| 缺陷 | 改动位置 | 方案 | 工时 |
|------|---------|------|------|
| 仅 1 个触发点 | `main.py:713` | 追加 `clear_inventory`、`delete_favorite_recipes` 到 `interrupt_on` 字典 | 0.5 天 |
| resume 不流式 | `chat_relay.py:256` | 改为 `fridge_graph.astream_events(Command(resume=...), version="v2")`，复用已有 `_handle_chat_stream` 逻辑 | 1.5 天 |
| 无 reject 分支 | `chat_relay.py:250-262` | `if decision == "reject": ...` 跳过该工具调用并通知用户 | 0.5 天 |
| 无超时清理 | `chat_relay.py` 新增 | 后台任务每 5 分钟扫描 checkpointer，清理超时中断 | 1 天 |
| 断线重连 | `chat_relay.py:201` | 连接时查询 `thread_id` 待处理中断，下发 `stream_interrupt` 通知 | 1 天 |
| REST 无恢复 | `routes/chat.py` 新增 | `POST /api/chat/resume` 端点，接受 `thread_id` + `decision` | 1 天 |

---

## P1-2: 工具返回结构不一致

### 当前状态

LLM 需要面对 6 种不同的工具返回格式，没有任何统一的成功/失败/空结果的约定：

| 工具 | 正常返回格式 | 异常返回格式 |
|------|------------|------------|
| `get_fridge_inventory` (L76-101) | `{"status": "ok", "total_items": N, "items": [...]}` | `{"status": "empty", "message": "...", "items": []}` |
| `search_recipes_by_ingredients` (L196) | `"[{...}, {...}]"` (纯 JSON list) | `"未找到匹配的菜谱。"` (纯文本，非 JSON) |
| `get_recipe_detail` (L223, L239) | `{"id": ..., "name": ..., "ingredients": [...], "steps": [...]}` | `{"error": "未找到菜谱 ID: xxx"}` |
| `recommend_by_fridge` (L377, L436, L446) | `{"status": "ok", "recipes": [...]}` | `{"status": "empty", ...}` / `{"status": "no_match", ...}` |
| 子 Agent (subagents.py) | `result["messages"][-1].content` (LLM raw 文本) | `"菜谱专家暂时无法响应: ..."` (截断纯文本) |
| `find_substitutions` (L283-291) | `{"ingredient": ..., "suggestions": ...}` | `{"error": ..., ...}` / `{"note": "LLM未初始化"}` |

核心问题：**LLM 每次解析工具返回需要猜测这是成功还是失败、数据在哪个 key 下。** 三种"成功"标记方式、三种"失败"返回方式共存。

### 改进方案

**第一步：定义统一响应模型（`api/tools.py` 新增）**

```python
@dataclass
class ToolResponse:
    """所有 @tool 函数的统一返回格式。"""
    success: bool
    data: Any = None
    error: str | None = None
    message: str | None = None

    def to_json(self) -> str:
        return json.dumps({
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "message": self.message,
        }, ensure_ascii=False, indent=2)

    @classmethod
    def ok(cls, data: Any = None, message: str = None) -> str:
        return cls(success=True, data=data, message=message).to_json()

    @classmethod
    def fail(cls, error: str, message: str = None) -> str:
        return cls(success=False, error=error, message=message).to_json()

    @classmethod
    def empty(cls, message: str = "没有找到结果") -> str:
        return cls(success=True, data=[], message=message).to_json()
```

**第二步：逐个工具改造（8 个工具 + 3 个子 Agent wrapper）**

```python
# search_recipes_by_ingredients — 旧:
if not results:
    return "未找到匹配的菜谱。"  # ← 纯文本
return json.dumps(results, ...)

# search_recipes_by_ingredients — 新:
if not results:
    return ToolResponse.empty("未找到匹配的菜谱，请调整搜索条件")
return ToolResponse.ok(data=results)

# get_recipe_detail — 旧:
return json.dumps({"error": f"未找到菜谱 ID: {recipe_id}"}, ...)

# get_recipe_detail — 新:
return ToolResponse.fail(error=f"未找到菜谱 ID: {recipe_id}")

# 子 Agent wrapper — 新:
return ToolResponse.ok(data={"answer": result["messages"][-1].content})
```

**改动量：** 8 个 `@tool` + 3 个子 Agent wrapper，约 2~3 天。Agent system_prompt 追加一条 "所有工具返回 `{"success": true/false, ...}` 格式" 提示。

---

## P1-3: Combined 路由退化为 Round-robin 盲插

### 当前状态

**文件：** `Backend/rag_modules/intelligent_query_router.py:147-184`

```python
def _combined_search(self, query: str, top_k: int) -> List[Document]:
    traditional_k = max(1, top_k // 2)
    graph_k = top_k - traditional_k

    traditional_docs = self.traditional_retrieval.hybrid_search(query, traditional_k)
    graph_docs = self.graph_rag_retrieval.graph_rag_search(query, graph_k)

    # 纯 Round-robin 交替穿插
    for i in range(max_len):
        if i < len(graph_docs):
            combined_docs.append(doc)           # ← 图结果优先，无质量信号
        if i < len(traditional_docs):
            combined_docs.append(doc)

    return combined_docs[:top_k]
```

零重叠场景（图 10 条、传统 20 条完全不重叠）→ Round-robin 是盲插，没有任何质量信号指导排序。代码注释 "先添加图RAG结果（通常质量更高）" 是没有数据支撑的假设。面试回答中讨论了 BGE-Reranker 和 RRF 方案但均未实现。

### 改进方案

**方案 A：RRF（1 天）**

```python
def _rrf_fuse(self, *result_lists: List[Document], k: int = 60) -> List[Document]:
    scores = {}
    all_docs = {}
    for docs in result_lists:
        for rank, doc in enumerate(docs):
            doc_id = doc.metadata.get("node_id", hash(doc.page_content))
            scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            all_docs[doc_id] = doc
    sorted_ids = sorted(scores, key=scores.get, reverse=True)
    return [all_docs[doc_id] for doc_id in sorted_ids[:top_k]]
```

**方案 B：Cross-encoder 重排序（论文加分，3~4 天）**

```python
from sentence_transformers import CrossEncoder
self.reranker = CrossEncoder("BAAI/bge-reranker-base")
pairs = [(query, doc.page_content) for doc in candidates]
scores = self.reranker.predict(pairs)
```

额外延迟约 100-200ms，精度提升可量化为 NDCG 改进。BGE-Reranker 约 300MB，与已有 embedding 模型共享 sentence-transformers 依赖。

---

## P1-4: Neo4j 无同义关系边 + 三个独立驱动实例

### 当前状态

**三个文件各自创建 Neo4j 驱动实例：**

| 文件 | 行号 | 代码 |
|------|------|------|
| `graph_data_preparation.py` | 60-64 | `self.driver = GraphDatabase.driver(uri, auth=(...), database=...)` |
| `hybrid_retrieval.py` | 67-71 | `self.driver = GraphDatabase.driver(config.neo4j_uri, auth=(...), database=...)` |
| `graph_rag_retrieval.py` | 83-87 | `self.driver = GraphDatabase.driver(config.neo4j_uri, auth=(...), database=...)` |

单个进程 3 个连接池，违反 Neo4j 官方推荐的单例驱动模式。

**图遍历无法跨同义词：** KG 中 `番茄` 和 `西红柿` 是独立节点。`MATCH (source)-[*1..{max_depth}]-(target)` 只能沿图中实际存在的边（REQUIRES、CONTAINS_STEP 等）走。同义词关系在 Python 层 `INGREDIENT_SYNONYMS` 字典中（`fuzzy_matcher.py:15-121`），图原生遍历完全看不到。

### 改进方案

**Neo4j 驱动统一（1 天）— 新增 `neo4j_client.py`：**

```python
class Neo4jClient:
    _driver = None
    @classmethod
    def get_driver(cls, uri, user, password, database="neo4j"):
        if cls._driver is None:
            cls._driver = GraphDatabase.driver(uri, auth=(user, password), database=database)
        return cls._driver
```

三个模块改为共享驱动。

**SAME_AS 边迁移（2 天）— 新增 `scripts/migrate_synonym_edges.py`：**

```python
for name, synonyms in INGREDIENT_SYNONYMS.items():
    for syn in synonyms:
        session.run("""
            MATCH (a:Ingredient), (b:Ingredient)
            WHERE a.name = $name1 AND b.name = $name2
            MERGE (a)-[:SAME_AS]->(b)
        """, name1=name, name2=syn)
```

图遍历兼容：`MATCH path = (source)-[:SAME_AS*0..]-(alias)-[*1..{max_depth}]-(target)`

---

## P1-5: 三种检索分数不可通约的加权融合 + BM25 未调优

### 当前状态

**文件：** `Backend/rag_modules/hybrid_retrieval.py:572-586`

```python
# 图索引 — Jaccard 关键词匹配 [0, 1] → × 0.2
doc.metadata["final_score"] = doc.metadata.get("relevance_score", 0.0) * 0.2

# 向量检索 — 余弦相似度 [0, 1] → × 0.5
doc.metadata["final_score"] = similarity * 0.5

# BM25 — 基于排名的离散值 → × 0.3
doc.metadata["final_score"] = (1.0 / (1.0 + rank)) * 0.3
# 值序列: 0.3, 0.15, 0.10, 0.075, 0.06...
```

BM25 第一名和第二名差 3 倍；向量第一名和第二名可能只差 0.03；图 Jaccard 分布极度右偏——三者直接相加等价于假设 "BM25 第一名 = 向量相似度 1.0 × 0.3" 是无理论依据的。

**BM25 同时未针对中文调优：** `hybrid_retrieval.py:75` — 使用默认参数（k1=1.5, b=0.75，无 jieba 分词器），中文字符级分词导致回召质量差。

### 改进方案

**分数归一化（1 天）：**

```python
def _min_max_normalize(docs, score_key):
    scores = [d.metadata.get(score_key, 0.0) for d in docs]
    min_s, max_s = min(scores), max(scores)
    if max_s == min_s:
        return docs
    for d in docs:
        d.metadata["norm_score"] = (d.metadata.get(score_key, 0.0) - min_s) / (max_s - min_s)
    return docs
```

三路结果各自归一化后再做 0.2/0.5/0.3 加权。更好的方案：直接改用 RRF（与 P1-3 方案 A 合并）。

**BM25 中文调优（1 天）：**

```python
import jieba
tokenized_chunks = [list(jieba.cut(doc.page_content)) for doc in chunks]
self.bm25 = BM25Okapi(tokenized_chunks, k1=1.2, b=0.5)
```

k1=1.2（低词频饱和度，食材名在菜谱中出现 1-2 次），b=0.5（降低文档长度归一化强度）。

---

## P1-6: 测试标准过低

已在 P0 分析中覆盖。核心数据点：

| 指标 | 当前阈值 | 合理阈值 |
|------|---------|---------|
| ContextPrecision | **0.25** (`test_retrieval_ragas.py:247`) | 0.60+ |
| ContextRecall | **0.18** (`test_retrieval_ragas.py:310`) | 0.50+ |
| Faithfulness | 0.30 | 0.70+ |
| 答案正确性 | 0.35 | 0.60+ |

另：解析失败的 JSON → `{"verdict": 1}` 无条件通过；`test_comprehensive` 使用缓存（只测生成不测检索）。缺少 WS 流式、HITL 恢复、并发、子 Agent 失败的集成测试。

**改进方向：** 阈值全线提升至 0.60+；`_repair_json_output` 改为 inconclusive 而非通过；`test_comprehensive` 不使用缓存；新增 4 类集成测试。

---

## P1-7: find_substitutions 使用独立模型实例

### 当前状态

**文件：** `Backend/api/tools.py:260-291`

```python
def find_substitutions(ingredient_name: str) -> str:
    from api.dependencies import fridge_model      # ← 独立模型实例
    response_msg = fridge_model.invoke([HumanMessage(content=prompt)])
    # ↑ 裸 LLM 调用，不经过 Agent 的五层中间件
```

`fridge_model` 来源 — `main.py:687`：`deps.fridge_model = model`（`create_agent()` 之前的 `init_chat_model()`）。此裸模型绕过调用限流、摘要压缩、HITL、模型重试、工具重试全部中间件。代码注释明确承认此缺陷（L260-263）。

### 改进方案

`find_substitutions` 改为纯检索工具（不做 LLM 调用），LLM 推理交由 `substitution_expert` 子 Agent 完成。最终删除 `deps.fridge_model`（`dependencies.py:41` 和 `main.py:687`）。

---

## P1-8: Neo4j 使用 CONTAINS 而非全文索引

### 当前状态

**文件：** `Backend/rag_modules/graph_rag_retrieval.py:198, 247, 268`

```python
WHERE source.name CONTAINS source_name OR source.nodeId = source_name
```

`CONTAINS` 在 Neo4j 中是全表顺序扫描（O(n)）。全文索引已在 `graph_data_preparation.py:78-96` 中创建，但 `GraphRAGRetrieval` 完全不使用。

### 改进方案

替换 3 处 `CONTAINS` 为 `CALL db.index.fulltext.queryNodes(...)` 全文索引查询。与 P1-4 的 Neo4j 驱动统一一起做。

---

## P1-9: cooking_knowledge 浮升因子 1.4 任意硬编码

### 当前状态

**文件：** `Backend/rag_modules/hybrid_retrieval.py:591-596`

```python
ck_boost = 1.0 if max_dual_score > 0.8 else 1.4
```

1.4 的浮升足以覆盖 0.3/0.5/0.2 融合权重体系，但来源无依据。

### 改进方案

移除硬编码浮升。改为在查询分析阶段识别"烹饪知识类查询"→ 路由分流调整融合权重（图 0.15、cooking_knowledge 0.05、向量 0.5、BM25 0.3）。用路由分流替代后置浮升。

---

## P1 改进优先级与时间估算

| 顺序 | 问题 | 工时 | 理由 |
|------|------|------|------|
| 1 | P1-7 find_substitutions 独立模型 | 1 天 | 正确性风险，修复简单 |
| 2 | P1-2 工具返回结构不一致 | 2~3 天 | 降低 LLM 出错率，影响面最大 |
| 3 | P1-4 Neo4j 驱动统一 + SAME_AS 边 | 3 天 | 结构性改进 |
| 4 | P1-8 CONTAINS → 全文索引 | 1 天 | 小改动，P1-4 配套 |
| 5 | P1-3 / P1-5 Round-robin + 分数融合 | 2~4 天 | 检索质量提升，论文加分 |
| 6 | P1-1 HITL 完善 | 5~7 天 | 工作量大，体验提升显著 |
| 7 | P1-9 cooking_knowledge 浮升 | 1 天 | 小改动 |
| 8 | P1-6 测试标准 | 持续 | 随其他改进同步提升 |

**P1 最小可行改进（2 周内）：**
P1-7 + P1-2 + P1-4 + P1-8 + P1-3 方案 A = 约 8~10 个工作日

---

> 所有代码引用基于 2026-07-23 源码版本，可在 `D:\Agent学习\FridgeApp\Backend\` 下验证。
