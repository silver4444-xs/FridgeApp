# FridgeAI — 智能冰箱食材管理与菜谱推荐系统

> 以下按简历项目经历的格式撰写，参考了业界 RAG/Agent 项目的描述风格，可直接用于简历。

---

## 版本 A：完整版（适合项目经历详细描述，~200 字/条）

### FridgeAI · 面向 IoT 智能冰箱的多 Agent 菜谱推荐与 GraphRAG 对话系统

**技术栈**: Python, LangChain 1.x, LangGraph 1.x, FastAPI, Neo4j, Milvus, DeepSeek API, MQTT, uni-app, WebSocket, Ragas, sentence-transformers

**项目描述**: 基于 LangGraph + GraphRAG 构建智能冰箱多 Agent 对话系统，融合 Neo4j 知识图谱与 Milvus 向量检索双引擎，实现食材管理、菜谱推荐、食材替换与烹饪问答的全链路智能化，覆盖 IoT 数据采集到 uni-app 多端交互。

- **多 Agent 协作架构**: 基于 LangGraph 1.x 设计 3 子 Agent 协作模式（菜谱专家 / 替换专家 / 烹饪专家），结合 Structured Output（response_format）约束子 Agent 输出格式，配合 5 层中间件（调用限流 / 摘要压缩 / HITL 人机审批 / 模型重试 / 工具重试）保障 Agent 稳定性和可控性，实现复杂烹饪场景下的任务拆解与精准路由。
- **GraphRAG 双引擎检索**: 构建 Neo4j 烹饪知识图谱（食材-菜谱-营养多跳关系）+ Milvus 向量索引（BAAI/bge-small-zh-v1.5 嵌入），设计双层检索范式（实体级 + 主题级）与 Round-robin 融合策略，结合 LLM 智能查询路由自动选择 hybrid / graph / combined 策略，实现多跳关系推理与语义检索的互补。
- **IoT 数据集成与实时推送**: 对接 OneNET 云平台 MQTT 协议，通过 RK3588 边缘节点上报冰箱食材数据，Backend Relay HTTP 轮询 + WebSocket 双向推送至 uni-app 前端，实现食材实时监控与过期预警。
- **检索增强与同义词扩展**: 构建 323 道菜谱倒排索引 + 40+ 组食材同义词映射（番茄↔西红柿），三层覆盖（索引构建 / 搜索展开 / 匹配校验）提升模糊搜索命中率，结合 jieba 分词与 BM25 关键词匹配保障稀疏查询场景下的召回质量。
- **RAG 评测体系**: 构建 50 条中文烹饪问答 Ragas 评测数据集（覆盖 11 个领域），实现 Context Precision / Recall / Faithfulness / Relevancy / Correctness 五项指标的自动化评测，适配 DeepSeek API（bypass n>1 限制 + NaN 安全过滤），首次评测平均检索耗时 ~16s/条。
- **流式对话与多端交互**: 基于 FastAPI WebSocket 实现 Agent 流式对话（astream_events v2），支持 tool_call / tool_error / token 级别事件推送，前端 uni-app 实现聊天气泡、富文本解析（Markdown 表格 / 代码块 / 引用）、HITL 审批卡片与自动滚动优化。

---

## 版本 B：精简版（适合简历空间有限，~120 字，合并为 3-4 条）

### FridgeAI · 基于 GraphRAG 与多 Agent 的智能冰箱对话系统

**技术栈**: Python, LangGraph 1.x, FastAPI, Neo4j, Milvus, DeepSeek, MQTT, WebSocket, Ragas

- 基于 LangGraph 构建 3 子 Agent 协作系统 + 5 层中间件（限流 / 摘要 / HITL / 重试），结合 Structured Output 约束子 Agent 输出，实现菜谱推荐、食材替换与烹饪问答的精准调度。
- 设计 Neo4j + Milvus 双引擎 GraphRAG 检索架构，双层检索范式（实体级 + 主题级）配合智能查询路由与 Round-robin 融合策略，结合 40+ 组同义词扩展与倒排索引提升混合检索召回质量。
- 对接 OneNET IoT MQTT 协议实现冰箱食材实时监控，FastAPI WebSocket 流式推送 Agent 对话至 uni-app 多端，支持富文本解析与 HITL 人机审批交互。
- 构建 50 条 Ragas 评测数据集（11 领域 x 5 指标），完成 RAG 检索 + 生成管道端到端评测，适配 DeepSeek API 并实现 NaN 安全过滤与指标均值计算。

---

## 版本 C：一句话版（适合技能总结或个人简介）

> 基于 LangGraph + GraphRAG（Neo4j + Milvus）构建的多 Agent 智能冰箱对话系统，3 子 Agent 协作 + 5 层中间件 + IoT MQTT 实时数据集成，覆盖检索、推荐、流式交互全链路，配套 Ragas 自动化评测体系。

---

## 可选亮点（面试时可展开）

| 亮点 | 说明 |
|------|------|
| **GraphRAG 双引擎** | Neo4j 多跳关系推理 + Milvus 语义检索，非简单的 RAG 问答 |
| **Multi-Agent 协作** | 3 子 Agent + Structured Output，有实际落地经验 |
| **5 层中间件** | HITL 人机审批、重试机制、摘要压缩，生产级考量 |
| **IoT 全链路** | 从 MQTT 边缘设备到前端 UI 的完整数据管道 |
| **RAG 评测体系** | Ragas 5 指标自动化评测，有量化结果 |
| **流式 WebSocket** | Token 级别流式推送 + tool 调用可视化 |
| **模糊搜索增强** | 40+ 同义词组 + 倒排索引 + BM25，多策略融合 |
