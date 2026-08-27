"""
共享中间件工厂 + CircuitBreakerMiddleware + InputGuardMiddleware

解决:
  P0-1: 子 Agent 中间件严重不足 (仅 1/5 层) — 统一工厂消除不一致
  P0-2: 无熔断机制 (外部依赖故障时雪崩) — CircuitBreakerMiddleware
  P1-1: 主/子 Agent 中间件参数不一致 — 工厂统一配置
  P1-A: 摘要用主模型浪费 token — summary_model 轻量模型
  P1-B: 无输入安全校验 — InputGuardMiddleware (长度+注入关键词)
"""
import json
import logging
import threading
import time
from typing import Optional

from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelRetryMiddleware,
    SummarizationMiddleware,
    ToolRetryMiddleware,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# InputGuardMiddleware (P1-B: 输入安全守卫)
# ═══════════════════════════════════════════════════════════════

class InputGuardMiddleware(AgentMiddleware):
    """用户输入安全守卫 —— before_model 钩子中校验最后一条 HumanMessage。

    防护:
    1. 消息长度限制（默认 2000 字符，超过则拒绝并返回友好提示）
    2. Prompt 注入关键词检测（中英文常见注入模式）
    3. 拒绝时通过 before_model 返回 AIMessage 直接应答，阻止进入 LLM

    放置位置:
        中间件列表 index 1（CircuitBreaker 之后，ModelCallLimit 之前）。
        仅主 Agent 添加；子 Agent 的输入已经由主 Agent 过滤。

    关键词列表涵盖:
        - 英文注入: "ignore previous instructions", "disregard", "system prompt"
        - 中文注入: "忽略之前的指令", "忽略上述指令", "忘记之前的所有"
        - Token smuggling: "<|im_start|>", "<|im_end|>" (ChatML 分隔符)
    """

    def __init__(
        self,
        max_length: int = 2000,
        blocked_patterns: list[str] | None = None,
    ):
        """初始化输入守卫。

        Args:
            max_length: 用户消息最大字符数（默认 2000）
            blocked_patterns: 注入关键词列表（大小写不敏感匹配）
        """
        super().__init__()
        self.max_length = max_length
        self.blocked_patterns = blocked_patterns or [
            # 英文注入
            "ignore previous instructions",
            "ignore all previous",
            "disregard previous",
            "forget all previous",
            # 中文注入
            "忽略之前的指令",
            "忽略上述指令",
            "忘记之前的所有",
            "不要管之前的",
            # Token smuggling
            "<|im_start|>",
            "<|im_end|>",
            "system prompt",
        ]

    def before_model(self, state, runtime):
        """在每次模型调用前检查最后一条用户消息。

        返回 None = 放行；返回 dict = 替换 state 中 messages，直接应答。
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # 找到最后一条 HumanMessage（用户输入）
        content = ""
        for msg in reversed(messages):
            if isinstance(msg, HumanMessage):
                content = getattr(msg, 'content', '') or ''
                break

        if not isinstance(content, str) or not content:
            return None

        # ── 长度检查 ──
        if len(content) > self.max_length:
            logger.warning(
                f"[InputGuard] 消息过长 ({len(content)} > {self.max_length})，"
                f"已拒绝 | 前50字: {content[:50]}..."
            )
            return {
                "messages": [
                    AIMessage(content=(
                        f"您的消息过长（{len(content)} 字，上限 {self.max_length} 字）。"
                        "请精简后重新发送。"
                    ))
                ]
            }

        # ── 注入关键词检查 ──
        content_lower = content.lower()
        for pattern in self.blocked_patterns:
            if pattern.lower() in content_lower:
                logger.warning(
                    f"[InputGuard] 检测到注入关键词 '{pattern}'，"
                    f"已拒绝 | 前50字: {content[:50]}..."
                )
                return {
                    "messages": [
                        AIMessage(content="您的消息包含不支持的指令，请重新描述您的需求。")
                    ]
                }

        return None  # 放行

    def describe(self) -> dict:
        """P2-B: 运行时自检 — 返回输入守卫配置。"""
        return {
            "type": "InputGuardMiddleware",
            "max_length": self.max_length,
            "patterns": len(self.blocked_patterns),
        }


# ═══════════════════════════════════════════════════════════════
# CircuitBreakerMiddleware (P0-2)
# ═══════════════════════════════════════════════════════════════

class CircuitBreakerMiddleware(AgentMiddleware):
    """工具调用熔断器 —— 防止外部依赖故障时的级联重试。

    状态机:
        CLOSED          —— 正常工作状态，失败计数递增
          │  (连续 N 次失败)
          ▼
        OPEN            —— 熔断打开，30s 内直接拒绝所有调用（不调用 handler）
          │  (冷却期满 30s)
          ▼
        HALF_OPEN       —— 半开状态，允许 1 次探测调用
          │
          ├── 探测成功 → CLOSED（恢复正常）
          └── 探测失败 → OPEN （重新熔断）

    放置位置:
        中间件列表 index 0（最外层）。当电路 OPEN 时直接返回 fast-fail
        ToolMessage，不执行后续 ModelCallLimit/Retry 等任何中间件。

    关键设计:
        ToolRetryMiddleware(on_failure="return_message") 会用 ToolMessage
        包裹错误而非抛出异常。因此熔断器通过 _is_error_result() 同时检测
        异常和错误 ToolMessage 返回值，确保两种失败路径都能正确触发熔断。

    线程安全:
        self._state dict 的所有读写由 threading.Lock() 保护。
        由于每个 FastAPI 请求可能在独立线程中 invoke 子 Agent，
        多个并发请求可能同时更新同一工具的熔断状态。

    并发隔离边界 (Phase 2 文档化):
        熔断状态是 **进程内** 的 (threading.Lock 只保护单进程内多线程)。
        - 单实例 / uvicorn 单 worker: 边界正确，熔断状态全进程共享。
        - uvicorn --workers N: 每个 worker 是独立进程，各自维护独立的
          熔断状态。某工具在一个 worker 熔断后，其余 worker 仍会继续
          调用该工具（故障计数在进程间不共享）。
        - K8s / 多实例部署: 同上，实例间熔断状态互不可见。
        多实例下如需全局一致的熔断，须替换为分布式熔断器 (如 Redis
        计数器 + TTL)。此为已知边界，单实例场景可接受，不阻塞当前阶段。
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        monitored_tools: Optional[list[str]] = None,
    ):
        """初始化熔断器。

        Args:
            failure_threshold: 连续失败次数阈值，达到后触发熔断（默认 3）
            cooldown_seconds: OPEN 状态冷却时间，超时后进入 HALF_OPEN（默认 30s）
            monitored_tools: 需要熔断保护的工具名列表。
                            None = 监控所有工具调用（默认）。
                            建议只监控依赖外部服务的工具（Neo4j/Milvus/DeepSeek）。
        """
        super().__init__()
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.monitored_tools = set(monitored_tools) if monitored_tools else None

        # 每工具独立状态
        # {
        #     "tool_name": {
        #         "failures": int,           # 连续失败计数
        #         "circuit_state": str,       # "CLOSED" | "OPEN" | "HALF_OPEN"
        #         "opened_at": float,         # 进入 OPEN 的时间戳
        #     }
        # }
        self._state: dict[str, dict] = {}
        self._lock = threading.Lock()

    # ── 内部辅助方法 ──

    def _should_track(self, tool_name: str) -> bool:
        """判断是否需要监控该工具。"""
        return self.monitored_tools is None or tool_name in self.monitored_tools

    def _get_state(self, tool_name: str) -> dict:
        """线程安全地读取某工具状态（返回副本，避免外部误修改）。"""
        with self._lock:
            entry = self._state.setdefault(tool_name, {
                "failures": 0,
                "circuit_state": "CLOSED",
                "opened_at": 0.0,
            })
            return dict(entry)

    def _transition_to(self, tool_name: str, new_state: str, failures: int = 0):
        """线程安全地转换工具状态并记录日志。"""
        with self._lock:
            old_state = self._state.get(tool_name, {}).get("circuit_state", "CLOSED")
            self._state[tool_name] = {
                "failures": failures,
                "circuit_state": new_state,
                "opened_at": time.time() if new_state == "OPEN" else 0.0,
            }
        if new_state == "OPEN" and old_state != "OPEN":
            logger.warning(
                f"[CircuitBreaker] {tool_name}: {old_state} → OPEN "
                f"(连续 {failures} 次失败, 冷却 {self.cooldown_seconds}s)"
            )
        elif new_state == "CLOSED" and old_state != "CLOSED":
            logger.info(f"[CircuitBreaker] {tool_name}: {old_state} → CLOSED (已恢复)")

    def _increment_failures(self, tool_name: str) -> str:
        """递增失败计数，达到阈值则触发熔断。返回当前状态。"""
        with self._lock:
            entry = self._state.setdefault(tool_name, {
                "failures": 0, "circuit_state": "CLOSED", "opened_at": 0.0,
            })
            entry["failures"] += 1
            new_count = entry["failures"]

        if new_count >= self.failure_threshold:
            # 达到阈值 → OPEN（或 HALF_OPEN 探测失败 → 回到 OPEN）
            self._transition_to(tool_name, "OPEN", failures=new_count)

        return self._get_state(tool_name)["circuit_state"]

    def _record_success(self, tool_name: str):
        """工具调用成功 → 重置为 CLOSED。"""
        old_state = self._get_state(tool_name)["circuit_state"]
        if old_state != "CLOSED":
            self._transition_to(tool_name, "CLOSED", failures=0)
        else:
            # 已经是 CLOSED，只需归零计数器（无需日志噪音）
            with self._lock:
                if tool_name in self._state:
                    self._state[tool_name]["failures"] = 0

    @staticmethod
    def _is_error_result(result) -> bool:
        """检测 ToolRetryMiddleware(on_failure='return_message') 返回的错误消息。

        背景: ToolRetryMiddleware 用 ToolMessage 包裹错误而非抛出异常。
        外层熔断器必须检查返回值，否则永远看不到失败。

        检测逻辑:
        1. ToolMessage.status == "error" → 错误
        2. ToolMessage.content 可解析为 {"success": false} → 错误（项目 ToolResponse 格式）
        3. Command.update.messages 中含有 error status 的 ToolMessage → 错误
        """
        # 方式 1: ToolMessage 显式 error 状态
        if isinstance(result, ToolMessage):
            if getattr(result, 'status', None) == 'error':
                return True
            # 方式 2: JSON 内容中 success=false（项目 ToolResponse 格式）
            content = getattr(result, 'content', '')
            if isinstance(content, str):
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and data.get("success") is False:
                        return True
                except (json.JSONDecodeError, TypeError):
                    # P2 消音: 非 JSON ToolMessage 内容（通常是普通文本，不是错误）
                    logger.debug(
                        f"[CircuitBreaker] ToolMessage 非 JSON: "
                        f"{str(content)[:100]}"
                    )
        # 方式 3: Command 中包裹的 error
        if isinstance(result, Command):
            update = getattr(result, 'update', None) or {}
            msgs = update.get("messages", [])
            for msg in msgs:
                if isinstance(msg, ToolMessage) and getattr(msg, 'status', None) == 'error':
                    return True
        return False

    # ── wrap_tool_call 钩子（核心）──

    def describe(self) -> dict:
        """P2-B: 运行时自检 — 返回所有工具的熔断状态。"""
        with self._lock:
            return {
                "type": "CircuitBreakerMiddleware",
                "threshold": self.failure_threshold,
                "cooldown_s": self.cooldown_seconds,
                "monitored_tools": (
                    sorted(self.monitored_tools) if self.monitored_tools else "ALL"
                ),
                "open_circuits": {
                    tool: s["failures"]
                    for tool, s in self._state.items()
                    if s["circuit_state"] != "CLOSED"
                },
                "total_tracked": len(self._state),
            }

    def wrap_tool_call(self, request, handler):
        """同步工具调用熔断（agent.invoke() 场景）。"""
        tool_call = getattr(request, 'tool_call', {})
        tool_name = tool_call.get("name", "unknown")

        # 不是监控目标 → 直接透传
        if not self._should_track(tool_name):
            return handler(request)

        state = self._get_state(tool_name)

        # ── OPEN 状态：快速失败 ──
        if state["circuit_state"] == "OPEN":
            elapsed = time.time() - state["opened_at"]
            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                logger.warning(
                    f"[CircuitBreaker] {tool_name} OPEN → 快速失败 "
                    f"(冷却剩余 {remaining:.0f}s)"
                )
                return ToolMessage(
                    content=(
                        f"工具「{tool_name}」暂时不可用（熔断保护中，"
                        f"预计 {remaining:.0f} 秒后自动恢复）"
                    ),
                    tool_call_id=tool_call.get("id", ""),
                    status="error",
                )
            else:
                self._transition_to(tool_name, "HALF_OPEN", failures=state["failures"])
                logger.info(
                    f"[CircuitBreaker] {tool_name}: OPEN → HALF_OPEN "
                    f"(冷却期满，允许探测)"
                )

        # ── CLOSED / HALF_OPEN：同步执行 ──
        try:
            result = handler(request)

            if self._is_error_result(result):
                error_content = getattr(result, 'content', '未知错误')
                self._increment_failures(tool_name)
                logger.debug(
                    f"[CircuitBreaker] {tool_name} 返回错误: "
                    f"{str(error_content)[:200]}"
                )
            else:
                self._record_success(tool_name)

            return result

        except Exception as e:
            self._increment_failures(tool_name)
            logger.debug(
                f"[CircuitBreaker] {tool_name} 抛出异常: {type(e).__name__}: {e}"
            )
            raise

    async def awrap_tool_call(self, request, handler):
        """异步工具调用熔断（agent.ainvoke() / graph.astream_events() 场景）。

        FridgeApp 通过 /ws/chat 使用 graph.astream_events(v2) 流式输出，
        因此异步版本是必需的。
        """
        tool_call = getattr(request, 'tool_call', {})
        tool_name = tool_call.get("name", "unknown")

        # 不是监控目标 → 直接透传
        if not self._should_track(tool_name):
            return await handler(request)

        state = self._get_state(tool_name)

        # ── OPEN 状态：快速失败 ──
        if state["circuit_state"] == "OPEN":
            elapsed = time.time() - state["opened_at"]
            if elapsed < self.cooldown_seconds:
                remaining = self.cooldown_seconds - elapsed
                logger.warning(
                    f"[CircuitBreaker] {tool_name} OPEN → 快速失败 "
                    f"(冷却剩余 {remaining:.0f}s)"
                )
                return ToolMessage(
                    content=(
                        f"工具「{tool_name}」暂时不可用（熔断保护中，"
                        f"预计 {remaining:.0f} 秒后自动恢复）"
                    ),
                    tool_call_id=tool_call.get("id", ""),
                    status="error",
                )
            else:
                self._transition_to(tool_name, "HALF_OPEN", failures=state["failures"])
                logger.info(
                    f"[CircuitBreaker] {tool_name}: OPEN → HALF_OPEN "
                    f"(冷却期满，允许探测)"
                )

        # ── CLOSED / HALF_OPEN：异步执行 ──
        try:
            result = await handler(request)  # 异步 handler 返回 coroutine，需要 await

            if self._is_error_result(result):
                error_content = getattr(result, 'content', '未知错误')
                self._increment_failures(tool_name)
                logger.debug(
                    f"[CircuitBreaker] {tool_name} 返回错误: "
                    f"{str(error_content)[:200]}"
                )
            else:
                self._record_success(tool_name)

            return result

        except Exception as e:
            self._increment_failures(tool_name)
            logger.debug(
                f"[CircuitBreaker] {tool_name} 抛出异常: {type(e).__name__}: {e}"
            )
            raise


# ═══════════════════════════════════════════════════════════════
# 共享中间件工厂
# ═══════════════════════════════════════════════════════════════

# 全部 11 个工具名（从 tools 列表提取 t.name，回退到此列表）
_ALL_TOOL_NAMES = [
    "get_fridge_inventory",
    "recommend_by_fridge",
    "search_recipes_by_ingredients",
    "get_recipe_detail",
    "find_substitutions",
    "search_cooking_knowledge",
    "save_user_preferences",
    "get_user_preferences",
    "recipe_expert",
    "substitution_expert",
    "cooking_expert",
]

# 需要熔断保护的工具（依赖外部服务: Neo4j / Milvus / DeepSeek API）
# 不包含纯本地操作: get_fridge_inventory / save_user_preferences / get_user_preferences
_CIRCUIT_BREAKER_TOOLS = [
    "recommend_by_fridge",
    "search_recipes_by_ingredients",
    "get_recipe_detail",
    "find_substitutions",
    "search_cooking_knowledge",
    "recipe_expert",
    "substitution_expert",
    "cooking_expert",
]


def create_fridge_middleware(
    model, tools, *,
    agent_type="main",
    summary_model=None,          # P1-A: 轻量摘要模型 (None=回退到 model)
    enable_input_guard=True,     # P1-B: 输入守卫 (仅 main 模式生效)
    enable_hitl=True,            # HITL 人工审批 (仅 main 模式生效, 测试可关闭)
):
    """创建 FridgeApp Agent 的统一中间件栈。

    消除主 Agent 和子 Agent 之间中间件配置的不一致，
    一处修改全局生效。

    Args:
        model: ChatModel 实例（主推理模型）
        tools: 工具列表（ToolRetryMiddleware 从中提取 t.name）
        agent_type: "main" | "subagent"
            "main"     → 7 层中间件（含 InputGuard + Summarization + HITL + CircuitBreaker）
            "subagent" → 4 层中间件（无 InputGuard/Summarization/HITL，run_limit 降至 10）
        summary_model: P1-A 轻量摘要模型（None 则回退到 model）
        enable_input_guard: P1-B 是否启用输入守卫（仅 main 模式生效）

    Returns:
        中间件列表，顺序已优化（index 0 = 最外层 = 最先拦截）:
        [CircuitBreaker, InputGuard?, ModelCallLimit, Summarization?, HITL?, ModelRetry, ToolRetry]

    中间件嵌套关系:
        CircuitBreaker.wrap()           # 最外层，电路 OPEN 时直接短路
          └─ InputGuard.before_model()  # 仅 main，检查用户输入
               └─ ModelCallLimit.wrap()
                    └─ Summarization.wrap()   # 仅 main（轻量模型）
                         └─ HITL.wrap()       # 仅 main
                              └─ ModelRetry.wrap()         # LLM API 重试
                                   └─ ToolRetry.wrap()      # 工具层重试
                                        └─ 实际工具/handler
    """
    is_main = (agent_type == "main")

    # 从 tools 列表提取工具名（回退到默认全部）
    tool_names = [t.name for t in tools] if tools else _ALL_TOOL_NAMES

    middleware = []

    # ── 0: 熔断器（最外层）──
    # 放在最外层，确保电路 OPEN 时快速失败，
    # 不经过后续的任何 Retry/Limit/Summarization 中间件
    middleware.append(CircuitBreakerMiddleware(
        failure_threshold=3,           # 3 次连续失败 → 熔断
        cooldown_seconds=30.0,         # 30 秒冷却后 HALF_OPEN 探测
        monitored_tools=_CIRCUIT_BREAKER_TOOLS,
    ))

    # ── 1: 输入守卫（仅主 Agent）──
    # P1-B: 消息长度限制 + Prompt 注入关键词检测
    # 子 Agent 不添加 — 输入已由主 Agent 过滤
    if is_main and enable_input_guard:
        middleware.append(InputGuardMiddleware(
            max_length=2000,            # 用户消息最大 2000 字符
        ))

    # ── 2: 模型调用上限 ──
    # 主 Agent 15 次（多轮对话 + 多次 tool-calling）
    # 子 Agent 10 次（单轮调用，1-3 次内部 tool 调用）
    middleware.append(ModelCallLimitMiddleware(
        run_limit=15 if is_main else 10,
        exit_behavior="end",          # 达到上限后优雅结束（不抛异常）
    ))

    # ── 3: 对话摘要（仅主 Agent）──
    # P1-A: 使用轻量 summary_model 替代主推理模型
    # 子 Agent 是单次 invoke 的短生命周期 Agent，无需长对话压缩
    if is_main:
        middleware.append(SummarizationMiddleware(
            model=summary_model or model,  # P1-A: 轻量模型，回退到主模型
            trigger=("tokens", 4000),      # 对话超 4000 token 触发摘要
            keep=("messages", 10),         # 保留最后 10 条消息原文
            summary_prompt=(
                "请用中文简洁总结以下对话的关键信息，包括：\n"
                "1. 用户提到的饮食偏好和忌口\n"
                "2. 讨论过并得到用户认可的菜谱\n"
                "3. 用户明确提出的需求或问题\n"
                "4. 重要的上下文信息\n\n"
                "对话内容:\n{messages}"
            ),
        ))

    # ── 4: 人工审批（仅主 Agent）──
    # 子 Agent 不执行 save_user_preferences（该工具仅主 Agent 持有）
    if is_main and enable_hitl:
        middleware.append(HumanInTheLoopMiddleware(
            interrupt_on={
                "save_user_preferences": {
                    "allowed_decisions": ["approve", "reject"],
                    "description": "保存用户饮食偏好到长期记忆",
                },
            },
            description_prefix="操作待确认",
        ))

    # ── 5: 模型调用重试 ──
    # 统一参数: 3 次重试 + 指数退避 + jitter 防惊群
    # 修复前子 Agent 为 max_retries=2, initial_delay=0.5, 无 jitter
    middleware.append(ModelRetryMiddleware(
        max_retries=3,
        backoff_factor=2.0,            # 延迟倍乘: 1s → 2s → 4s
        initial_delay=1.0,             # 首次重试延迟 1s
        max_delay=30.0,                # 单次延迟上限
        jitter=True,                   # 随机抖动，防惊群效应
    ))

    # ── 5: 工具调用重试（最内层）──
    # 覆盖全部 11 个工具（修复前仅 5 个）
    # on_failure="return_message": 重试耗尽后返回错误消息给 LLM（而非抛异常）
    middleware.append(ToolRetryMiddleware(
        max_retries=2,
        tools=tool_names,              # 覆盖全部 11 个工具
        initial_delay=0.5,
        max_delay=10.0,
        backoff_factor=2.0,
        jitter=True,
        on_failure="return_message",   # 最终失败 → 返回错误消息给 LLM
    ))

    return middleware
