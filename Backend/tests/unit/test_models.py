"""Pydantic 模型验证 — RecipeSummary/Detail 默认值 + Agent 结构化输出模型"""
import pytest
from api.models import (
    RecipeSummary, RecipeDetail,
    AgentRecommendResponse, AgentRecipeItem,
    AgentSubstitutionResponse, AgentSubstitutionItem,
)


# ─── 菜谱 Pydantic 模型: 默认值 + 字段验证 ───
class TestRecipeModels:
    def test_summary_defaults(self):
        """RecipeSummary 默认值: category="其他", difficulty="未知" """
        r = RecipeSummary(id="r001", name="测试")
        assert r.category == "其他" and r.difficulty == "未知"

    def test_detail_creation(self):
        """RecipeDetail 创建: steps 长度校验, tips 默认为空字符串"""
        r = RecipeDetail(id="r001", name="番茄炒蛋",
                         ingredients=[{"name": "鸡蛋"}], steps=["打蛋", "炒"])
        assert len(r.steps) == 2 and r.tips == ""


# ─── Agent 结构化输出模型: 菜谱推荐响应 + 食材替换响应 ───
class TestAgentStructuredOutput:
    def test_recommend_response(self):
        """AgentRecommendResponse 序列化: 推荐列表 + JSON 导出含菜名"""
        resp = AgentRecommendResponse(
            recommendations=[
                AgentRecipeItem(name="番茄炒蛋", match_count=2, total_ingredients=2,
                                missing=[], difficulty="简单", time="15分钟")],
            fridge_summary="冰箱有4种食材")
        assert len(resp.recommendations) == 1
        assert "番茄炒蛋" in resp.model_dump_json()

    def test_substitution_response(self):
        """AgentSubstitutionResponse 序列化: 原始食材→替代方案映射"""
        resp = AgentSubstitutionResponse(
            suggestions=[
                AgentSubstitutionItem(
                    original="黄油", alternatives=["橄榄油", "椰子油"],
                    impact="口味略有变化")],
            summary="可用橄榄油替代")
        assert resp.suggestions[0].original == "黄油"