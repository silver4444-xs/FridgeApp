"""8个 @tool 函数单元测试 — mock 隔离 recipe_db/inverted_index/store 外部依赖"""
import json, pytest
from unittest.mock import MagicMock, patch


# ─── get_fridge_inventory — 读取冰箱食材清单 (空/有食材) ───
class TestGetFridgeInventory:
    def test_empty(self):
        """空冰箱: status="empty" """
        from api.tools import get_fridge_inventory, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(current_inventory=[], user_id="u1")
        assert json.loads(get_fridge_inventory.func(runtime))["status"] == "empty"

    def test_with_items(self, sample_inventory):
        """有食材: status="ok", total_items=12"""
        from api.tools import get_fridge_inventory, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(current_inventory=sample_inventory, user_id="u1")
        r = json.loads(get_fridge_inventory.func(runtime))
        assert r["status"] == "ok" and r["total_items"] == 12


# ─── search_recipes_by_ingredients — 按食材名显式搜索菜谱 ───
class TestSearchRecipesByIngredients:
    def test_match_found(self, mock_recipe_db, mock_inverted_index):
        """搜索"鸡蛋+西红柿"应返回含"番茄炒蛋"的结果"""
        with patch("api.dependencies.recipe_db", mock_recipe_db), \
             patch("api.dependencies.inverted_index", mock_inverted_index):
            from api.tools import search_recipes_by_ingredients
            r = json.loads(search_recipes_by_ingredients.func(["鸡蛋", "西红柿"]))
            assert any("番茄炒蛋" == x["name"] for x in r)

    def test_no_match(self, mock_recipe_db, mock_inverted_index):
        """搜索不存在的食材返回"未找到" """
        with patch("api.dependencies.recipe_db", mock_recipe_db), \
             patch("api.dependencies.inverted_index", mock_inverted_index):
            from api.tools import search_recipes_by_ingredients
            assert "未找到" in search_recipes_by_ingredients.func(["不存在的食材XYZ"])


# ─── get_recipe_detail — 按菜谱ID获取完整详情 ───
class TestGetRecipeDetail:
    def test_existing(self, mock_recipe_db):
        """获取存在的菜谱详情: 含 name + steps 字段"""
        with patch("api.dependencies.recipe_db", mock_recipe_db):
            from api.tools import get_recipe_detail
            r = json.loads(get_recipe_detail.func("r001"))
            assert r["name"] == "番茄炒蛋" and len(r["steps"]) > 0

    def test_nonexistent(self, mock_recipe_db):
        """获取不存在的菜谱返回 error 字段"""
        with patch("api.dependencies.recipe_db", mock_recipe_db):
            from api.tools import get_recipe_detail
            assert "error" in json.loads(get_recipe_detail.func("nope"))


# ─── recommend_by_fridge — 基于冰箱食材推荐: 忌口过滤 + 匹配度排序 ───
class TestRecommendByFridge:
    def test_dietary_filter(self, mock_recipe_db, mock_inverted_index):
        """忌口过滤: 用户忌口"花生"→推荐结果不应含"宫保鸡丁" """
        from api.tools import recommend_by_fridge, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(
            current_inventory=[
                {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
                {"name": "鸡胸肉", "qty": 2, "cat": "肉蛋生鲜类"},
                {"name": "花生", "qty": 1, "cat": "包装食品类"},
            ],
            user_preferences={"忌口": ["花生"]}, user_id="u1")
        with patch("api.dependencies.recipe_db", mock_recipe_db), \
             patch("api.dependencies.inverted_index", mock_inverted_index):
            r = json.loads(recommend_by_fridge.func(runtime))
            names = [x["name"] for x in r.get("recipes", [])]
            assert "宫保鸡丁" not in names  # 含花生被过滤

    def test_match_sorting(self, mock_recipe_db, mock_inverted_index):
        """匹配度排序: 第1个菜谱的 match_count ≥ 第2个"""
        from api.tools import recommend_by_fridge, FridgeContext
        runtime = MagicMock()
        runtime.context = FridgeContext(
            current_inventory=[
                {"name": "鸡蛋", "qty": 6, "cat": "肉蛋生鲜类"},
                {"name": "牛奶", "qty": 1, "cat": "饮料乳品类"},
            ], user_preferences={}, user_id="u1")
        with patch("api.dependencies.recipe_db", mock_recipe_db), \
             patch("api.dependencies.inverted_index", mock_inverted_index):
            r = json.loads(recommend_by_fridge.func(runtime))
            recipes = r.get("recipes", [])
            if len(recipes) >= 2:
                assert recipes[0]["match_count"] >= recipes[1]["match_count"]


# ─── save/get_user_preferences — 用户偏好持久化 (InMemoryStore) ───
class TestSaveGetPreferences:
    def test_save_and_get(self):
        """保存偏好后立即读取: 写入"忌口:花生"→读取应返回相同值"""
        from api.tools import save_user_preferences, get_user_preferences, FridgeContext
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        r1 = MagicMock(); r1.store = store
        r1.context = FridgeContext(user_id="u_test")
        r = json.loads(save_user_preferences.func({"忌口": ["花生"]}, r1))
        assert r["status"] == "ok"

        r2 = MagicMock(); r2.store = store
        r2.context = FridgeContext(user_preferences={}, user_id="u_test")
        r = json.loads(get_user_preferences.func(r2))
        assert r["preferences"]["忌口"] == ["花生"]

    def test_merge_existing(self):
        """偏好合并: 先存"忌口:花生", 再存"人数:3"→合并后两者共存"""
        from api.tools import save_user_preferences, FridgeContext
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        ctx = FridgeContext(user_id="u_test")
        r1 = MagicMock(); r1.store = store; r1.context = ctx
        save_user_preferences.func({"忌口": ["花生"]}, r1)
        r2 = MagicMock(); r2.store = store; r2.context = ctx
        r = json.loads(save_user_preferences.func({"人数": 3}, r2))
        assert r["saved"]["忌口"] == ["花生"] and r["saved"]["人数"] == 3