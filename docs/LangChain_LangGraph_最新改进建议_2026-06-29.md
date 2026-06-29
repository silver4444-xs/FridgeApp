# FridgeAI LangChain + LangGraph 最新改进建议

> 基于 LangChain v1.3 / LangGraph v1.2 官方 API (2026-06-29)
> 仅提供分析建议，不修改源代码

---

## 一、当前状态回顾

### Phase 1-6 全部完成

| Phase | 内容 |
|-------|------|
| Phase 1 | `create_agent` + `@tool` × 6 + `ToolRuntime` |
| Phase 2 | `StateGraph` + `InMemorySaver` 多轮对话 |
| Phase 3 | 5 层 Middleware (CallLimit/Summarization/HITL/ModelRetry/ToolRetry) |
| Phase 3.5 | `InMemoryStore` Long-term Memory |
| Phase 4 | `HumanInTheLoopMiddleware` 写操作审批 |
| Phase 5 | `/ws/chat` `astream_events(v3)` 流式输出 |
| Phase 6 | 3 子 Agent Subagents 多 Agent 协作 |

### 核心差距

1. **全 InMemory 存储**: Store/Checkpointer 重启全丢
2. **无生产级可观测性**: 无 LangSmith tracing
3. **Subagents 冷启动**: 每次 `new create_agent()`，首次延迟 500ms+
4. **无结构化输出**: Agent 自由文本，前端难解析
5. **Graph 单节点**: 仅 1 个 `recommend` 节点，内部不可见
6. **前端对话未接入**: `/ws/chat` 后端就绪，前端 recipes.vue 未适配

---

## 二、改进优先级总览

| 优先级 | 改进项 | 改动量 | 收益 |
|--------|--------|--------|------|
| **P0** | PostgresSaver + PostgresStore 持久化 | ~20行 | 重启不丢数据 |
| **P0** | LangSmith 全链路追踪 | 3 env var | Agent 内部可见 |
| **P1** | Structured Output 结构化响应 | ~40行 | 前端可解析 |
| **P1** | 前端 Agent 对话接入 | ~100行 | 用户真正可用 |
| **P2** | Graph Prompt Chaining 多节点 | ~100行 | 步骤可观测 |
| **P2** | LangGraph Functional API 食材 CRUD | ~30行 | 确定性流程轻量化 |
| **P3** | Subagents 缓存优化 | ~50行 | 调用 500ms→10ms |
| **P3** | Model Profile 自适应配置 | ~10行 | 换模型零配置 |

---

## 三、P0: Postgres 持久化

仅改 import + 连接字符串，代码逻辑零改动：

```python
# 改造前
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

# 改造后
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore

DB_URI = "postgresql://postgres:postgres@localhost:5432/fridgeai?sslmode=disable"
store = AsyncPostgresStore.from_conn_string(DB_URI)
checkpointer = AsyncPostgresSaver.from_conn_string(DB_URI)
```

收益: 服务重启不丢对话历史+偏好；多实例共享数据。

---

## 四、P0: LangSmith 追踪

3 个环境变量：

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=ls_...
export LANGSMITH_PROJECT=fridgeai
```

收益: 可视化 Agent 执行链路（LLM call → tool call → 下一个 LLM call），自动统计 token 消耗。

---

## 五、P1: Structured Output

LangChain v1 支持 `response_format`，Agent 返回 Pydantic 模型：

```python
from pydantic import BaseModel, Field

class RecipeRecommendation(BaseModel):
    recipe_name: str
    match_count: int
    missing_ingredients: list[str]

class RecommendResponse(BaseModel):
    recommendations: list[RecipeRecommendation]
    fridge_summary: str

agent = create_agent(
    model=model,
    tools=[recipe_expert, ...],
    response_format=RecommendResponse,  # 自动选最佳策略
)
# result["structured_response"] → RecommendResponse 实例
```

Model Profile 自动检测 provider 是否支持原生 structured output（OpenAI/Anthropic/xAI 支持），不支持的自动降级为 tool-calling 策略。

适用: `recipe_expert` 返回 `RecommendResponse`；`substitution_expert` 返回 `SubstitutionResponse`。

---

## 六、P1: 前端 Agent 对话接入

`/ws/chat` 已就绪，前端新增 `agentChat.js` + `recipes.vue` 对话输入框：

```
用户: "能做什么菜" → stream_token: "您可以" → stream_token: "做红烧肉" → ...
                      stream_tool_start: recommend_by_fridge
                      stream_tool_end: 找到 5 道菜
                      stream_done
```

前端按消息类型渲染：`stream_token` 打字机效果，`stream_tool_start/end` 状态提示卡片。

---

## 七、P2: Graph Prompt Chaining

`graph.py` 中已有注释代码（Phase 2.2），激活四节点流水线：

```
analyze_inventory → search_recipes → rank_results → generate_response
```

每个节点独立可观测（LangSmith 中可见输入/输出），问题定位从 "Agent 推荐不对" 精确到 "排序分数偏低"。

---

## 八、P2: Functional API 食材 CRUD

LangGraph v1.2 Functional API (`@entrypoint` + `@task`) 替代重 StateGraph：

```python
from langgraph.func import entrypoint, task

@task
def validate_food_item(item: dict) -> dict:
    if not item.get("name"): raise ValueError("名称不能为空")
    return item

@entrypoint(checkpointer=InMemorySaver())
def add_food_workflow(foods: list[dict]) -> dict:
    results = [validate_food_item(f).result() for f in foods]
    return {"added": len(results), "items": results}
```

适用: 确定性步骤链（添加食材/删除食材/生成购物清单），无需 LLM 决策，需 checkpoint 持久化。

---

## 九、P3: Subagents 缓存 + Model Profile

**缓存**: `@functools.lru_cache` 缓存子 Agent 实例，首次调用后复用，延迟从 500ms 降至 ~10ms。

**Model Profile**: `SummarizationMiddleware` 改用 `trigger=("fraction", 0.85)` 替代硬编码 `trigger=("tokens", 4000)`。切换模型（DeepSeek 64K → GPT-5.5 400K）时自动适配。

---

## 十、不改动部分

- `onenet_relay.py` HTTP 轮询 + 上传队列（确定性 I/O）
- `ws_relay.py` WebSocket 客户端池
- `matching/` 倒排索引 + 模糊匹配
- `rag_modules/` Neo4j + Milvus 检索
- 前端 `store.js` 数据中心

---

## 十一、实施路线图

```
Phase 7 (P0) — 持久化 + 追踪           ~30行 + 3 env
Phase 8 (P1) — 结构化输出 + 前端对话    ~140行
Phase 9 (P2) — 多节点 Graph + Func API ~130行
Phase 10 (P3)— 缓存 + Model Profile     ~60行
```

全量实施后，FridgeAI 从"功能完整"升级为"生产就绪"。
