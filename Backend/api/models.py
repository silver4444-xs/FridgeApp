"""API Pydantic models — called by api/routes/*"""
from pydantic import BaseModel, Field
from typing import List, Optional


class IngredientInput(BaseModel):
    name: str
    cat: str = "other"
    qty: float = 1
    unit: str = "个"


class RecommendRequest(BaseModel):
    ingredients: List[IngredientInput]
    limit: int = Field(default=20, ge=1, le=100)
    min_match: int = Field(default=1, ge=0)


class RecipeSummary(BaseModel):
    id: str
    name: str
    image: Optional[str] = None
    category: str = "其他"
    difficulty: str = "未知"
    time: str = "未知"
    ingredients: List[str] = []
    matchCount: int = 0
    totalIngredients: int = 0
    matchRatio: float = 0.0
    ownedIngredients: List[str] = []
    missingIngredients: List[str] = []
    steps: List[str] = []
    tags: List[str] = []


class RecommendMeta(BaseModel):
    total_matched: int
    fridge_items_count: int


class RecommendResponse(BaseModel):
    recipes: List[RecipeSummary]
    meta: RecommendMeta


class RecipeDetail(BaseModel):
    id: str
    name: str
    image: Optional[str] = None
    category: str = "其他"
    difficulty: str = "未知"
    time: str = "未知"
    ingredients: List[dict] = []
    steps: List[str] = []
    tips: str = ""
    tags: List[str] = []
    source: str = ""


class SubstitutionRequest(BaseModel):
    missing_ingredients: List[str]
    available_ingredients: List[str]


class SubstitutionResponse(BaseModel):
    substitutions: List[dict]
    summary: str = ""


# ═══════════════════════════════════════════════════════════════
# Phase 8: Agent Structured Output 模型
# ═══════════════════════════════════════════════════════════════
# 原代码: Agent 返回自由文本，前端需正则/JSON 解析
# 改进后: create_agent(response_format=PydanticModel)
#   LangChain 自动选择最佳策略 (ProviderStrategy vs ToolStrategy)
#   Model Profile 自动检测 provider 是否支持原生 structured output


class AgentRecipeItem(BaseModel):
    """单道菜谱推荐"""
    name: str = Field(description="菜谱名称")
    match_count: int = Field(description="匹配的食材数")
    total_ingredients: int = Field(description="菜谱所需食材总数")
    missing: List[str] = Field(description="缺少的食材列表")
    difficulty: str = Field(description="难度: 简单/中等/困难")
    time: str = Field(description="预计烹饪时间")


class AgentRecommendResponse(BaseModel):
    """菜谱推荐结构化响应 — recipe_expert 子 Agent 使用"""
    recommendations: List[AgentRecipeItem] = Field(description="推荐菜谱列表")
    fridge_summary: str = Field(description="冰箱库存概况")


class AgentSubstitutionItem(BaseModel):
    """单条替换建议"""
    original: str = Field(description="需要替换的食材")
    alternatives: List[str] = Field(description="替代食材列表")
    impact: str = Field(description="对口味/口感的影响")


class AgentSubstitutionResponse(BaseModel):
    """食材替换结构化响应 — substitution_expert 子 Agent 使用"""
    suggestions: List[AgentSubstitutionItem] = Field(description="替换建议列表")
    summary: str = Field(description="总体建议")
