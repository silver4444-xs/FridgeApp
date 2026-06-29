"""
Phase 1: Agent 标准化 —— @tool 装饰器包装检索函数

将现有匹配/检索能力封装为标准 LangChain @tool，供 create_agent 使用。
LLM 可自主决定何时调用这些工具，替代手工编排的"路由→检索→生成"流程。

Phase 1.3: ToolRuntime 上下文注入
工具可通过 ToolRuntime 自动获取当前冰箱食材、用户偏好等上下文，
无需 LLM 每次手动传递食材列表。

原代码保留在各源文件中（matching/、api/routes/、main.py），
此处为 LangChain Agent 接口层，不修改原有业务逻辑。
"""
import json
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from langchain.tools import tool, ToolRuntime

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 上下文数据模型
# ═══════════════════════════════════════════════════════════════
# 原代码: 冰箱食材通过 WS food_update 推送至前端 store.js
#   store._foods → 前端 computed foods → 编辑时 uploadViaWs(store.foods)
# 改进后: 后端 Agent 通过 ToolRuntime.context 获取当前冰箱快照，
#   无需前端/LLM 显式传递食材列表。
# ═══════════════════════════════════════════════════════════════


@dataclass
class FridgeContext:
    """冰箱上下文 —— 每次 Agent 调用时注入的运行时数据。

    通过 agent.invoke(..., context=FridgeContext(...)) 传入，
    工具函数内通过 runtime.context 访问。
    """
    # ── 原字段 (Phase 1.3): ──
    # current_inventory: List[dict]
    # user_preferences: dict
    #
    # ── 改进后 (Phase 3.5: Long-term Memory): ──
    # 新增 user_id 字段，配合 InMemoryStore 实现跨会话偏好持久化
    # user_preferences 保留作为单次调用的 fallback（首次对话无历史时使用）
    current_inventory: List[dict] = field(default_factory=list)
    """当前冰箱食材快照，每项格式: {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"}"""

    user_preferences: dict = field(default_factory=dict)
    """用户偏好 (单次调用 fallback)，如 {"忌口": ["花生", "海鲜"], "偏好菜系": "川菜", "人数": 2}"""

    user_id: str = "default"
    """用户标识，用于 Store namespace 隔离。生产环境应从请求上下文注入。"""


# ═══════════════════════════════════════════════════════════════
# Tool 0: 获取冰箱当前食材 (ToolRuntime 上下文注入)
# ═══════════════════════════════════════════════════════════════
# 原代码: 前端 store.foods 通过 WS cloudSync.uploadViaWs() 上传
#   后端 relay._last_value 存储最新管道格式快照
# 改进后: 后端 Agent 通过 runtime.context.current_inventory 直接读取，
#   省去 LLM 显式传参环节。用户问「能做什么菜」时无需罗列食材。
# ═══════════════════════════════════════════════════════════════

@tool
def get_fridge_inventory(runtime: ToolRuntime[FridgeContext]) -> str:
    """获取冰箱当前存放的全部食材清单。包含食材名称、数量、分类和卡路里。

    适用场景:
    - 用户问「冰箱里有什么」→ 直接返回食材清单
    - 用户问「能做什么菜」→ 先调用此工具获取食材，再调用 search_recipes_by_ingredients
    - 用户未明确列举食材时，此工具自动提供上下文

    Returns:
        JSON格式的冰箱食材清单
    """
    # ── 原代码: store.js mergeCloudFoods() ──
    # store.mergeCloudFoods(cloudFoods)
    #   → translateFoodName(cf.name)  # EN→ZH 翻译
    #   → classifyFood(cf.name).cat   # 自动分类
    #   → 合并去重(qty累加)
    #   → store._save()  # 本地持久化
    # ────────────────────────────────────

    inventory = runtime.context.current_inventory

    if not inventory:
        return json.dumps({
            "status": "empty",
            "message": "冰箱里暂时没有食材。请先添加食材到冰箱。",
            "items": [],
        }, ensure_ascii=False)

    # 汇总统计
    total_items = sum(item.get("qty", 0) for item in inventory)
    categories = list(set(item.get("cat", "其他") for item in inventory))

    result = {
        "status": "ok",
        "total_items": total_items,
        "categories": categories,
        "items": [],
    }

    for item in inventory:
        result["items"].append({
            "name": item.get("name", ""),
            "quantity": item.get("qty", 0),
            "calories": item.get("cal", item.get("calories", None)),
            "category": item.get("cat", "其他"),
        })

    return json.dumps(result, ensure_ascii=False, indent=2)


# ── Tool 0 (旧版, 无可用的 runtime 时回退) ──
# @tool
# def get_fridge_inventory() -> str:
#     """获取冰箱当前食材清单。"""
#     from api.dependencies import get_onenet_relay
#     relay = get_onenet_relay()
#     if not relay or not relay._last_value:
#         return json.dumps({"status": "empty", "message": "冰箱暂未同步数据"})
#     items = parse_compact_inventory(relay._last_value)
#     return json.dumps(items, ensure_ascii=False, indent=2)
# 原逻辑位于 api/routes/recommend.py:recommend()
#   倒排索引查找 → 模糊匹配 → 排序 → 返回
# 改造后：包装为 @tool，LLM 可主动调用
# ═══════════════════════════════════════════════════════════════

@tool
def search_recipes_by_ingredients(ingredients: List[str], limit: int = 5) -> str:
    """根据冰箱现有食材搜索可制作的菜谱。返回匹配的菜谱列表，包含菜名、匹配食材数、难度和时间。

    Args:
        ingredients: 食材名称列表，如 ['鸡蛋', '西红柿', '鸡胸肉']
        limit: 返回结果数量上限，默认5

    Returns:
        JSON格式的匹配菜谱列表
    """
    # ── 原代码: api/routes/recommend.py ──
    # @router.post("/recommend", response_model=RecommendResponse)
    # def recommend(req: RecommendRequest, db=..., idx=...):
    #     fridge_names = FuzzyMatcher.normalize_fridge_items(
    #         [{"name": ing.name, "cat": ing.cat} for ing in req.ingredients])
    #     candidate_ids = idx.fuzzy_lookup(fridge_names)
    #     for rid in candidate_ids:
    #         recipe = db.get(rid)
    #         ...  # 匹配+排序逻辑
    # ──────────────────────────────────────

    from api.dependencies import recipe_db, inverted_index
    from matching.fuzzy_matcher import FuzzyMatcher

    # Fix #4: 食材名归一化时保留分类信息
    # 原有逻辑: 全部食材标为 "packaged"，丢失分类信息 → 模糊匹配精度下降
    # 修复后: 尝试通过中文名反查分类 (fallback 到 "packaged")
    _CN_CAT_MAP = {
        '水果': 'fruit', '蔬菜': 'vegetable', '肉蛋生鲜类': 'meat_egg',
        '饮料乳品类': 'beverage_dairy', '包装食品类': 'packaged',
        '肉蛋生鲜': 'meat_egg', '饮料乳品': 'beverage_dairy', '包装食品': 'packaged',
        '肉类': 'meat_egg', '海鲜': 'meat_egg', '乳品': 'beverage_dairy', '零食': 'packaged',
    }
    norm_items = []
    for ing in ingredients:
        cat = "packaged"
        if isinstance(ing, dict):
            cat = _CN_CAT_MAP.get(ing.get("cat", ""), ing.get("cat", "packaged"))
            name = ing.get("name", str(ing))
        else:
            name = str(ing)
        norm_items.append({"name": name, "cat": cat})

    fridge_names = FuzzyMatcher.normalize_fridge_items(norm_items)

    # 倒排索引查找候选菜谱
    candidate_ids = inverted_index.fuzzy_lookup(fridge_names)

    results = []
    for rid in candidate_ids:
        recipe = recipe_db.get(rid)
        if not recipe:
            continue

        matched = []
        missing = []
        for ing in recipe.get("ingredients", []):
            if FuzzyMatcher.is_match(ing, fridge_names):
                matched.append(ing["name"])
            elif ing.get("required", True):
                missing.append(ing["name"])

        match_count = len(matched)
        total = len([i for i in recipe.get("ingredients", [])
                     if i.get("required", True)])

        results.append({
            "id": recipe["id"],
            "name": recipe["name"],
            "category": recipe.get("category", "其他"),
            "difficulty": recipe.get("difficulty", "未知"),
            "time": recipe.get("time", "未知"),
            "match_count": match_count,
            "total_ingredients": total,
            "matched": matched,
            "missing": missing,
        })

    results.sort(key=lambda r: r["match_count"], reverse=True)
    results = results[:limit]

    if not results:
        return "未找到匹配的菜谱。请尝试添加更多食材或调整搜索条件。"

    return json.dumps(results, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# Tool 2: 获取菜谱详情
# ═══════════════════════════════════════════════════════════════
# 原逻辑位于 api/routes/detail.py:get_recipe()
#   recipe_db.get(recipe_id) → RecipeDetail Pydantic 模型
# 改造后：包装为 @tool，LLM 在需要详情时调用
# ═══════════════════════════════════════════════════════════════

@tool
def get_recipe_detail(recipe_id: str) -> str:
    """获取指定菜谱的完整详情，包括食材清单、制作步骤和小贴士。
    首次调用 search_recipes_by_ingredients 后，可用返回的 recipe id 查询详情。

    Args:
        recipe_id: 菜谱ID（从 search_recipes_by_ingredients 返回结果中获取）

    Returns:
        JSON格式的菜谱详细信息
    """
    # ── 原代码: api/routes/detail.py ──
    # @router.get("/{recipe_id}", response_model=RecipeDetail)
    # def get_recipe(recipe_id: str, db=...):
    #     recipe = db.get(recipe_id)
    #     if not recipe: raise HTTPException(404)
    #     return RecipeDetail(id=recipe["id"], name=recipe["name"], ...)
    # ──────────────────────────────────────

    from api.dependencies import recipe_db

    recipe = recipe_db.get(recipe_id)
    if not recipe:
        return json.dumps(
            {"error": f"未找到菜谱 ID: {recipe_id}"},
            ensure_ascii=False,
        )

    detail = {
        "id": recipe["id"],
        "name": recipe["name"],
        "category": recipe.get("category", "其他"),
        "difficulty": recipe.get("difficulty", "未知"),
        "time": recipe.get("time", "未知"),
        "ingredients": [i["name"] for i in recipe.get("ingredients", [])],
        "steps": recipe.get("steps", []),
        "tips": recipe.get("tips", ""),
        "tags": recipe.get("tags", []),
    }
    return json.dumps(detail, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# Tool 3: 食材替换建议
# ═══════════════════════════════════════════════════════════════
# 原逻辑位于 api/routes/substitutions.py:suggest()
#   LLM prompt → generation_module.generate_adaptive_answer()
# 改造后：包装为 @tool，LLM Agent 可自主触发替换查询
# ═══════════════════════════════════════════════════════════════

@tool
def find_substitutions(ingredient_name: str) -> str:
    """查找某食材的替代品建议。当冰箱缺少某食材时，可查询替代方案。

    Args:
        ingredient_name: 需要替换的食材名称，如 '黄油'、'牛奶'

    Returns:
        JSON格式的替代品建议
    """
    # ── 原代码: api/routes/substitutions.py ──
    # @router.post("/{recipe_id}/suggest-substitutions")
    # def suggest(recipe_id, req, db=...):
    #     prompt = f"你是一位专业厨师。用户想做{recipe['name']}..."
    #     response = rag.generation_module.generate_adaptive_answer(prompt, [])
    #     return SubstitutionResponse(...)
    # ──────────────────────────────────────
    # Fix #14: 备用 LLM 降级策略 (已知限制)
    # 当前 find_substitutions 使用 rag_system.generation_module.lc_client (独立 ChatOpenAI 实例)
    # 与 Agent 主模型不同，可能导致回答风格不一致。
    # 未来改进: 将 Agent 模型通过 runtime.context 注入，或使用 ToolRuntime.store 缓存结果。

    from api.dependencies import rag_system

    if not rag_system or not rag_system.generation_module:
        return json.dumps({
            "ingredient": ingredient_name,
            "suggestions": [f"{ingredient_name} 可在超市购买或尝试省略"],
            "note": "（LLM 未初始化，无法生成智能替换建议）",
        }, ensure_ascii=False)

    prompt = (
        f"你是一位专业厨师。用户想做菜但缺少食材「{ingredient_name}」。\n"
        f"请为该食材建议2-3种可行的替代方案，并简要说明每种替代对口味的影响。"
    )

    try:
        response = rag_system.generation_module.generate_adaptive_answer(
            prompt, []
        )
        return json.dumps({
            "ingredient": ingredient_name,
            "suggestions": response,
        }, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({
            "ingredient": ingredient_name,
            "error": f"生成建议失败: {str(e)}",
        }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# Tool 4: 烹饪知识 RAG 检索
# ═══════════════════════════════════════════════════════════════
# 原逻辑位于 main.py:AdvancedGraphRAGSystem.ask_question_with_routing()
#   智能路由 → 混合检索(HybridRetrieval + GraphRAG) → LLM 生成回答
# 改造后：包装为 @tool，Agent 可将其作为知识检索工具调用
# ═══════════════════════════════════════════════════════════════

@tool
def search_cooking_knowledge(question: str) -> str:
    """搜索烹饪知识库（RAG混合检索 + 图RAG），回答烹饪技巧、菜品知识等开放性问题。
    适用于: 烹饪技巧问答、菜系知识、食材处理方法等。

    Args:
        question: 烹饪相关问题，如 '如何让鸡肉更嫩?'、'川菜有什么特点?'

    Returns:
        基于知识库的综合回答
    """
    # ── 原代码: main.py:AdvancedGraphRAGSystem.ask_question_with_routing ──
    # def ask_question_with_routing(self, question, stream=False, explain_routing=False):
    #     # 1. 智能路由检索
    #     relevant_docs, analysis = self.query_router.route_query(question, self.config.top_k)
    #     # 2. 显示路由信息
    #     # 3. 生成回答
    #     result = self.generation_module.generate_adaptive_answer(question, relevant_docs)
    #     return result, analysis
    # ────────────────────────────────────────────────────────────────────

    from api.dependencies import rag_system

    if not rag_system or not rag_system.system_ready:
        return json.dumps({
            "error": "烹饪知识库未就绪，请稍后重试",
        }, ensure_ascii=False)

    try:
        result, analysis = rag_system.ask_question_with_routing(
            question, stream=False
        )
        return result if isinstance(result, str) else str(result)
    except Exception as e:
        return json.dumps({
            "error": f"知识检索失败: {str(e)}",
        }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# Tool 5: 基于冰箱上下文的智能推荐 (ToolRuntime 核心用例)
# ═══════════════════════════════════════════════════════════════
# 这是 Phase 1.3 的核心工具 —— 利用 ToolRuntime 自动获取冰箱食材，
# 用户只需说「能做什么菜」无需罗列食材，Agent 自动从上下文提取。
# ═══════════════════════════════════════════════════════════════

@tool
def recommend_by_fridge(
    runtime: ToolRuntime[FridgeContext],
    limit: int = 5,
) -> str:
    """基于冰箱当前食材智能推荐可制作的菜谱。自动读取冰箱库存，无需手动提供食材列表。

    适用场景:
    - 用户问「能做什么菜」「推荐几道菜」→ 自动基于冰箱食材推荐
    - 用户问「冰箱里这些能做什么」→ 无需重复列举食材
    - 每次推荐前先调用 get_fridge_inventory 了解库存状况

    Args:
        limit: 返回结果数量上限，默认5

    Returns:
        JSON格式的推荐结果，含菜谱列表和匹配统计
    """
    # ── 原代码: 前端 recipes.vue fetchRecommend() ──
    # async fetchRecommend() {
    #     const ingredients = store.foods.map(f => ({name: f.name, cat: f.cat, ...}))
    #     const res = await uni.request({
    #         url: getApiBase() + '/recipes/recommend', method: 'POST',
    #         data: { ingredients, limit: 50, min_match: 1 }
    #     })
    #     this.recommendRecipes = res.data.recipes
    # }
    # ── 原代码: api/routes/recommend.py:recommend() ──
    # fridge_names = FuzzyMatcher.normalize_fridge_items(
    #     [{"name": ing.name, "cat": ing.cat} for ing in req.ingredients])
    # candidate_ids = idx.fuzzy_lookup(fridge_names)
    # ... 匹配+排序 → RecommendResponse
    # ─────────────────────────────────────────────────────────────

    from api.dependencies import recipe_db, inverted_index
    from matching.fuzzy_matcher import FuzzyMatcher

    # 关键: 从 runtime.context 自动获取冰箱食材，无需 LLM 传参
    inventory = runtime.context.current_inventory
    prefs = runtime.context.user_preferences

    if not inventory:
        return json.dumps({
            "status": "empty",
            "message": "冰箱里暂时没有食材。请先用「添加食材」功能放入食材，我再为您推荐菜谱。",
            "recipes": [],
        }, ensure_ascii=False)

    # 归一化冰箱中的食材名
    fridge_names = FuzzyMatcher.normalize_fridge_items([
        {"name": item.get("name", ""), "cat": item.get("cat", "packaged")}
        for item in inventory
    ])

    # 倒排索引查找候选菜谱
    candidate_ids = inverted_index.fuzzy_lookup(fridge_names)

    # 用户偏好过滤关键词
    avoid_list = prefs.get("忌口", [])

    results = []
    for rid in candidate_ids:
        recipe = recipe_db.get(rid)
        if not recipe:
            continue

        matched = []
        missing = []
        for ing in recipe.get("ingredients", []):
            if FuzzyMatcher.is_match(ing, fridge_names):
                matched.append(ing["name"])
            elif ing.get("required", True):
                missing.append(ing["name"])

        match_count = len(matched)
        total = len([i for i in recipe.get("ingredients", [])
                     if i.get("required", True)])

        # 用户忌口过滤
        if avoid_list:
            recipe_text = recipe.get("name", "") + " ".join(
                i["name"] for i in recipe.get("ingredients", []))
            if any(av in recipe_text for av in avoid_list):
                continue

        results.append({
            "id": recipe["id"],
            "name": recipe["name"],
            "category": recipe.get("category", "其他"),
            "difficulty": recipe.get("difficulty", "未知"),
            "time": recipe.get("time", "未知"),
            "match_count": match_count,
            "total_ingredients": total,
            "matched": matched,
            "missing": missing,
        })

    results.sort(key=lambda r: r["match_count"], reverse=True)
    results = results[:limit]

    if not results:
        return json.dumps({
            "status": "no_match",
            "message": "冰箱中有 {} 种食材，但暂未找到匹配的菜谱。试试添加更多食材。".format(
                len(inventory)),
            "available_ingredients": [
                item.get("name", "") for item in inventory
            ],
            "recipes": [],
        }, ensure_ascii=False)

    return json.dumps({
        "status": "ok",
        "fridge_items_count": len(inventory),
        "total_matched": len(results),
        "recipes": results,
    }, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════
# Long-term Memory 工具 (Phase 3.5: InMemoryStore)
# ═══════════════════════════════════════════════════════════════
# 原代码: 用户偏好仅通过 FridgeContext.user_preferences 在单次调用中传递
#   每次新对话用户需重新声明忌口/偏好菜系
# 改进后: 通过 runtime.store 持久化偏好，跨会话自动继承
#   - save_user_preferences: Agent 检测到用户声明的偏好时自动保存
#   - get_user_preferences: 每次对话开始时自动读取历史偏好
# Store 模式: namespace=("preferences",), key=user_id, value=dict
# ═══════════════════════════════════════════════════════════════

@tool
def save_user_preferences(
    preferences: dict,
    runtime: ToolRuntime[FridgeContext],
) -> str:
    """保存用户饮食偏好到长期记忆。偏好将跨会话持久化，下次对话自动生效。

    适用场景:
    - 用户说「我不吃辣」「我对花生过敏」→ 保存忌口
    - 用户说「我喜欢川菜」「我们3个人吃饭」→ 保存偏好菜系和人数
    - Agent 检测到新的用户偏好时主动保存

    Args:
        preferences: 要保存的偏好键值对，如 {"忌口":["花生"],"偏好菜系":"川菜","人数":2}
                     支持部分更新 — 只传需要变更的字段即可

    Returns:
        JSON 格式的保存确认
    """
    # ── 原代码: 无长期记忆，偏好仅在 FridgeContext.user_preferences 中 ──
    # agent.invoke(..., context=FridgeContext(
    #     current_inventory=[...],
    #     user_preferences={"忌口":["花生"]},  # 每次调用都需显式传入
    # ))
    # ── 改进后: runtime.store 持久化 ──
    store = runtime.store
    user_id = runtime.context.user_id

    # 读取已有偏好并合并（新值覆盖旧值）
    existing = store.get(("preferences",), user_id)
    if existing and existing.value:
        merged = {**existing.value, **preferences}
    else:
        merged = preferences

    store.put(("preferences",), user_id, merged)
    return json.dumps({
        "status": "ok",
        "message": f"已保存 {len(merged)} 项偏好到长期记忆",
        "saved": merged,
    }, ensure_ascii=False, indent=2)


@tool
def get_user_preferences(
    runtime: ToolRuntime[FridgeContext],
) -> str:
    """读取用户已保存的饮食偏好（跨会话持久化）。

    适用场景:
    - 对话开始时自动调用，获取用户忌口、偏好菜系等
    - 用户问「你知道我的喜好吗」→ 返回已保存的偏好
    - recommend_by_fridge 调用前自动获取忌口列表进行过滤

    Returns:
        JSON 格式的用户偏好，首次使用返回空
    """
    # ── 原代码: 无长期记忆 ──
    # 偏好来源: runtime.context.user_preferences (单次调用有效)
    # ── 改进后: runtime.store 跨会话读取 ──
    store = runtime.store
    user_id = runtime.context.user_id

    prefs = store.get(("preferences",), user_id)
    if prefs and prefs.value:
        return json.dumps({
            "status": "ok",
            "preferences": prefs.value,
        }, ensure_ascii=False, indent=2)

    # 回退到 context 中的偏好 (首次对话无历史时)
    fallback = runtime.context.user_preferences
    if fallback:
        return json.dumps({
            "status": "ok",
            "source": "context (本次会话有效，未持久化)",
            "preferences": fallback,
        }, ensure_ascii=False, indent=2)

    return json.dumps({
        "status": "empty",
        "message": "暂无保存的饮食偏好。您可以告诉我您的忌口、偏好菜系等信息，我会记住。",
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════
# 工具列表汇总（供 create_agent 使用）
# ═══════════════════════════════════════════════════════════════

FRIDGE_TOOLS = [
    search_recipes_by_ingredients,
    get_recipe_detail,
    find_substitutions,
    search_cooking_knowledge,
]

# Phase 1.3 增强版工具列表 —— 包含 ToolRuntime 上下文感知工具
# recommend_by_fridge 可替代 search_recipes_by_ingredients 的多数场景，
# 用户无需显式列举食材，Agent 自动从 runtime.context 读取冰箱快照。
#
# ── Phase 3.5: Long-term Memory 工具 ──
# save_user_preferences / get_user_preferences 需 ToolRuntime + store,
# 仅加入 V2 (V1 无 context_schema 和 store 支持)
FRIDGE_TOOLS_V2 = [
    get_fridge_inventory,          # ToolRuntime: 读取冰箱食材清单
    recommend_by_fridge,            # ToolRuntime: 基于上下文自动推荐
    search_recipes_by_ingredients,  # 保留: 支持LLM显式传参场景
    get_recipe_detail,
    find_substitutions,
    search_cooking_knowledge,
    save_user_preferences,          # ★ Phase 3.5: Store 持久化偏好
    get_user_preferences,           # ★ Phase 3.5: Store 读取历史偏好
]

# Phase 6 Subagents: V3 用 3 个子 Agent 替代 5 个单体 tool
# 原 V2 8 个 tool → V3 6 个 (3 主 Agent 直属 + 3 子 Agent)
# recipe_expert 替代: recommend_by_fridge + search_recipes_by_ingredients + get_recipe_detail
# substitution_expert 替代: find_substitutions
# cooking_expert 替代: search_cooking_knowledge
FRIDGE_TOOLS_V3 = [
    get_fridge_inventory,           # 保留: 读取冰箱食材 (需 ToolRuntime)
    save_user_preferences,          # 保留: Store 持久化偏好
    get_user_preferences,           # 保留: Store 读取历史偏好
    # 3 个子 Agent 工具 (从 api/subagents.py 导入, 在 main.py 中合并)
]
