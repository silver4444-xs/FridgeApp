"""RecipeDatabase — 菜谱内存数据库 CRUD: 按ID获取/全量列表/按菜名搜索/字段类型验证"""
import pytest


# ─── 菜谱数据库 CRUD + Fix#9 字段类型验证 ───
class TestRecipeDatabase:
    # ── get() — 按ID获取单条菜谱 ──
    def test_get_existing(self, mock_recipe_db):
        """获取存在的菜谱: r001=番茄炒蛋, difficulty=简单"""
        r = mock_recipe_db.get("r001")
        assert r["name"] == "番茄炒蛋" and r["difficulty"] == "简单"

    def test_get_nonexistent(self, mock_recipe_db):
        """获取不存在的菜谱返回 None"""
        assert mock_recipe_db.get("nonexistent") is None

    # ── all() — 全量菜谱列表 ──
    def test_all_count(self, mock_recipe_db):
        """全量菜谱数量等于 mock 数据集大小 (3)"""
        assert len(mock_recipe_db.all()) == 3

    # ── search_names() — 按菜名搜索 ──
    def test_search_names_exact(self, mock_recipe_db):
        """精确搜索菜名: "番茄炒蛋" 命中 r001"""
        assert "r001" in mock_recipe_db.search_names("番茄炒蛋")

    def test_search_names_partial(self, mock_recipe_db):
        """模糊搜索菜名: "宫保" 命中 "宫保鸡丁" """
        assert "r002" in mock_recipe_db.search_names("宫保")

    def test_search_names_no_match(self, mock_recipe_db):
        """无匹配搜索返回空列表"""
        assert mock_recipe_db.search_names("佛跳墙") == []

    # ── 元信息 ──
    def test_len(self, mock_recipe_db):
        """__len__ 返回菜谱总数"""
        assert len(mock_recipe_db) == 3

    # ── Fix#9: 字段类型安全 ──
    def test_fields_are_strings(self, mock_recipe_db):
        """Fix #9: difficulty/time/category 等字段必须是 str 类型, 防止 float→Pydantic 500"""
        for r in mock_recipe_db.all():
            assert isinstance(r.get("difficulty"), str)
            assert isinstance(r.get("time"), str)
            assert isinstance(r.get("category"), str)