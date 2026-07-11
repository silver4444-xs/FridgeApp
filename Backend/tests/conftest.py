import sys, os
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def sample_inventory():
    return [
        {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"},
        {"name": "西红柿", "qty": 3, "cal": 18, "cat": "蔬菜"},
        {"name": "鸡胸肉", "qty": 2, "cal": 133, "cat": "肉蛋生鲜类"},
        {"name": "牛奶", "qty": 1, "cal": 65, "cat": "饮料乳品类"},
    ]


@pytest.fixture
def sample_preferences():
    return {"忌口": ["花生", "海鲜"], "偏好菜系": "川菜", "人数": 2}


@pytest.fixture
def sample_recipes():
    return [
        {
            "id": "r001", "name": "番茄炒蛋", "category": "家常菜",
            "difficulty": "简单", "time": "15分钟",
            "ingredients": [
                {"name": "鸡蛋", "required": True},
                {"name": "番茄", "required": True},
                {"name": "葱", "required": False},
            ],
            "steps": ["打蛋", "炒蛋", "炒番茄", "混合"],
            "tips": "火候要快", "tags": ["快手菜", "下饭"],
        },
        {
            "id": "r002", "name": "宫保鸡丁", "category": "川菜",
            "difficulty": "中等", "time": "30分钟",
            "ingredients": [
                {"name": "鸡胸肉", "required": True},
                {"name": "花生", "required": True},
                {"name": "干辣椒", "required": True},
            ],
            "steps": ["切丁", "腌制", "炒制"],
            "tips": "花生最后放保持脆度", "tags": ["川菜", "下饭"],
        },
        {
            "id": "r003", "name": "牛奶炖蛋", "category": "甜品",
            "difficulty": "简单", "time": "20分钟",
            "ingredients": [
                {"name": "鸡蛋", "required": True},
                {"name": "牛奶", "required": True},
                {"name": "糖", "required": False},
            ],
            "steps": ["打蛋", "加牛奶", "蒸"],
            "tips": "小火慢蒸", "tags": ["甜品", "快手"],
        },
    ]


@pytest.fixture
def mock_recipe_db(sample_recipes):
    from matching.recipe_database import RecipeDatabase
    db = RecipeDatabase()
    db._recipes.clear()
    for r in sample_recipes:
        db._recipes[r["id"]] = r
        for ch in r["name"].replace(" ", ""):
            db._name_index.setdefault(ch, set()).add(r["id"])
    return db


@pytest.fixture
def mock_inverted_index(sample_recipes):
    from matching.inverted_index import InvertedIndex
    idx = InvertedIndex()
    idx.build(sample_recipes)
    return idx