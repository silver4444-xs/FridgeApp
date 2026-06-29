# Session Summary — FridgeAI Backend

> 日期: 2026-06-22 | 供下一次 Agent 会话快速载入上下文

---

## 项目概览

**FridgeAI** — 基于 OneNET IoT 云平台的智能冰箱食材管理与菜谱推荐系统。

- **RK3588 边缘节点** → MQTT (`mqtts.heclouds.com:1883`) → OneNET → Backend HTTP 轮询 → WebSocket → uni-app 前端
- **OneNET 产品**: `OAgTJW6fph`，主设备: `device_01`
- **后端启动**: `cd Backend && uvicorn api.server:app --host 0.0.0.0 --port 8000 --reload`
- **Python**: 3.9+，类型注解使用 `Optional[X]`

---

## 当前系统架构

```
FastAPI (api/server.py)
├── OneNet Relay (api/onenet_relay.py)       — HTTP 500ms 轮询 + WS 推送 + 假数据回退
├── WebSocket Relay (api/ws_relay.py)         — /ws/fridge 端点 + client pool + broadcast
├── Recipe Routes (api/routes/)               — recommend/search/detail/substitutions
│
├── GraphRAG System (main.py)                 — AdvancedGraphRAGSystem
│   ├── GraphDataPreparation (rag_modules/)   — Neo4j → Document → Chunk
│   ├── MilvusIndexConstruction (rag_modules/) — BGE-small-zh-v1.5 嵌入 + HNSW 索引
│   ├── HybridRetrieval (rag_modules/)        — 双层检索 (实体+主题) + BM25 + 向量 + Round-robin
│   ├── GraphRAGRetrieval (rag_modules/)      — LLM→Cypher 图查询 + 多跳遍历 + 子图提取
│   ├── IntelligentQueryRouter (rag_modules/) — LLM 分析查询 → 自动路由策略
│   ├── GraphIndexing (rag_modules/)          — 实体/关系 KV 键值对索引
│   └── GenerationIntegration (rag_modules/)  — ChatOpenAI (DeepSeek) 答案生成 + 流式
│
├── Matching (matching/)                      — 倒排索引 + 模糊匹配 + 食材提取
└── Legacy RAG (原 FAISS+BM25)                 — 已移除，被 GraphRAG 替代
```

### LLM 客户端架构 (Step 0 已完成)

```
generation_integration.py:
  self.lc_client = ChatOpenAI(
      model="deepseek-v4-pro",
      base_url="https://api.deepseek.com/v1",
      stream_chunk_timeout=120,
  )
  │
  ├── self.lc_client.invoke(prompt)           — generate_adaptive_answer()
  ├── self.lc_client.stream(prompt)           — generate_adaptive_answer_stream()
  │
  └── 通过 main.py 注入 lc_client 到:
      ├── HybridRetrievalModule → self.llm_client.invoke(prompt, max_tokens=500)
      ├── GraphRAGRetrieval → self.llm_client.invoke(prompt, max_tokens=1000)
      ├── IntelligentQueryRouter → self.llm_client.invoke(prompt, max_tokens=800)
      └── GraphIndexingModule → self.llm_client.invoke(prompt, max_tokens=200)
```

---

## 本次会话变更清单

### 1. 系统修复 (6 文件)

| 文件 | 问题 | 修复 |
|------|------|------|
| `api/server.py` | `RecipeRAGSystem` 不存在 | 改为 `AdvancedGraphRAGSystem` + 文档元数据映射 |
| `api/routes/substitutions.py` | `generate_basic_answer()` 不存在 | 改为 `generate_adaptive_answer()` |
| `rag_modules/__init__.py` | 缺少类导出 | 新增 `GraphRAGRetrieval`, `IntelligentQueryRouter`, `QueryAnalysis` |
| `requirements.txt` | 缺少 neo4j, pymilvus, numpy | 新增 3 个依赖 |
| `matching/ingredient_extractor.py` | 不兼容 GraphRAG 文档格式 | 5 处: 新旧 section header 双支持、编号列表、步骤块、括号用量去除、后缀描述去除 |
| `rag_modules/graph_rag_retrieval.py` + `hybrid_retrieval.py` | Neo4j 驱动缺 database 参数 | 补齐 `database=neo4j_database` |

### 2. OneNET 云端回退

- `api/onenet_relay.py`: `FAKE_INVENTORY_PIPE` (12 种冰箱食材) + `FALLBACK_FAILURE_THRESHOLD=3`
- 云端不可用约 1.5 秒后自动推送假数据，仅推送一次

### 3. Step 0: OpenAI → ChatOpenAI

- `generation_integration.py`: 移除了 `openai.OpenAI`，仅保留 `ChatOpenAI(model=..., stream_chunk_timeout=120)`
- `main.py`: 3 处 `self.generation_module.client` → `lc_client`
- 4 个消费模块: `client.chat.completions.create()` → `llm_client.invoke(prompt, max_tokens=N)`

### 4. 文档

| 文件 | 内容 |
|------|------|
| `docs/LangChain生态重构分析.md` | 9 章框架级分析 |
| `docs/LangChain改进切入点分析.md` | Step 0 完成后的剩余路线图 |
| `docs/SESSION_SUMMARY.md` | 本文件 |

---

## 当前各模块状态

| 模块 | 状态 | 说明 |
|------|------|------|
| `api/server.py` | ✅ | AdvancedGraphRAGSystem + adapted_docs 适配层 |
| `api/onenet_relay.py` | ✅ | 含假数据回退机制 |
| `api/ws_relay.py` | ✅ | 无变更 |
| `api/routes/*` | ✅ | 4 条路由均正常 |
| `main.py` | ✅ | 传递 lc_client 到 4 个消费模块 |
| `config.py` | ✅ | GraphRAGConfig: neo4j://localhost:7687, milvus:19530, deepseek-v4-pro |
| `rag_modules/generation_integration.py` | ✅ | ChatOpenAI: invoke() + stream() |
| `rag_modules/graph_rag_retrieval.py` | ✅ | LLM→Cypher + 多跳遍历 + database 参数 |
| `rag_modules/hybrid_retrieval.py` | ✅ | 双层检索 + Round-robin + database 参数 |
| `rag_modules/intelligent_query_router.py` | ✅ | LLM 分析 + 策略路由 |
| `rag_modules/graph_indexing.py` | ✅ | KV 索引 |
| `rag_modules/milvus_index_construction.py` | ✅ | HNSW+COSINE |
| `rag_modules/graph_data_preparation.py` | ✅ | Neo4j→Document→Chunk |
| `matching/*` | ✅ | 新旧格式双支持 |
| `agent(代码系ai生成)/` | ⚠️ | 独立脚本，仍用原始 OpenAI 客户端 |

---

## 关键配置

| 配置 | 值 |
|------|-----|
| Neo4j URI | `bolt://localhost:7687` |
| Neo4j DB | `neo4j` (密码: `all-in-rag`) |
| Milvus | `localhost:19530` |
| 集合名 | `cooking_knowledge` |
| 嵌入模型 | `BAAI/bge-small-zh-v1.5` (512 维) |
| LLM | `deepseek-v4-pro` via `https://api.deepseek.com/v1` |
| 环境变量 | `DEEPSEEK_API_KEY` |

---

## 已知限制

1. `set-device-property` HTTP API 不更新 OneNET 属性历史 — 已通过 `_latest_upload` 缓解
2. RK3588 端缺失 `thing/property/post` 回传
3. 无自动化测试
4. 管道格式分隔符冲突风险
5. `agent(代码系ai生成)/` 未迁移到 ChatOpenAI
6. `with_structured_output()` 与 DeepSeek 兼容性待验证

---

## 下一步建议

```
Step 1: with_structured_output()    [~2h] — 消除 4 处裸 JSON 解析
Step 2: LangSmith 挂载              [~0.5h] — 零代码获得全链路 trace
Step 3: Prompt 模板提取             [~4h] — prompts/*.py
Step 4: LCEL 链式组合               [~8h] — RunnableParallel + .with_fallbacks()
Step 5: LangGraph StateGraph        [~2d] — 可视化工作流
```
