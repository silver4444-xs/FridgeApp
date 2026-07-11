"""FuzzyMatcher — 食材名归一化 + 别名匹配 + 同义词字典完整性验证"""
import pytest
from matching.fuzzy_matcher import FuzzyMatcher, INGREDIENT_SYNONYMS


# ─── normalize() 静态方法 — 食材名清洗: 去前缀/去单位/去数字/小写化 ───
class TestNormalize:
    def test_strip_whitespace(self):
        """去除前后空白字符"""
        assert FuzzyMatcher.normalize("  鸡蛋  ") == "鸡蛋"

    def test_remove_modifier_prefix(self):
        """去除修饰前缀: "有机西兰花"→"西兰花", "进口牛奶"→"牛奶" """
        assert FuzzyMatcher.normalize("有机西兰花") == "西兰花"
        assert FuzzyMatcher.normalize("进口牛奶") == "牛奶"

    def test_remove_unit_suffix(self):
        """去除数量+单位后缀: "鸡蛋6个"→"鸡蛋", "牛奶500ml"→"牛奶" """
        assert FuzzyMatcher.normalize("鸡蛋6个") == "鸡蛋"
        assert FuzzyMatcher.normalize("牛奶500ml") == "牛奶"

    def test_remove_gram_suffix(self):
        """去除克重后缀: "鸡胸肉500g"→"鸡胸肉" """
        assert FuzzyMatcher.normalize("鸡胸肉500g") == "鸡胸肉"

    def test_lowercase(self):
        """英文食材名统一小写: "Egg"→"egg" """
        assert FuzzyMatcher.normalize("Egg") == "egg"

    def test_remove_trailing_digits(self):
        """去除尾部纯数字: "鸡蛋3"→"鸡蛋" """
        assert FuzzyMatcher.normalize("鸡蛋3") == "鸡蛋"


# ─── is_match() 方法 — 单个食材与冰箱食材集匹配: 精确/同义词/子串/别名 ───
class TestIsMatch:
    def test_exact_match(self):
        """精确匹配: 食材名完全相同则命中"""
        assert FuzzyMatcher.is_match({"name": "鸡蛋"}, {"鸡蛋", "西红柿"})

    def test_synonym_match(self):
        """同义词匹配: 番茄↔西红柿 双向互查"""
        assert FuzzyMatcher.is_match({"name": "番茄"}, {"西红柿", "鸡蛋"})
        assert FuzzyMatcher.is_match({"name": "西红柿"}, {"番茄", "鸡蛋"})

    def test_substring_match(self):
        """子串匹配: "鸡胸肉" 包含 "鸡胸" 子串则命中"""
        assert FuzzyMatcher.is_match({"name": "鸡胸肉"}, {"鸡胸", "鸡蛋"})

    def test_no_match(self):
        """无匹配: 食材不在冰箱中且无同义词/子串关系"""
        assert not FuzzyMatcher.is_match({"name": "牛肉"}, {"鸡蛋", "西红柿"})

    def test_alias_match(self):
        """别名匹配: 食材 aliases 字段中的别名也可命中"""
        assert FuzzyMatcher.is_match(
            {"name": "猪肉", "aliases": ["五花肉"]}, {"五花肉", "鸡蛋"})


# ─── normalize_fridge_items() — 整批冰箱食材归一化 + 同义词展开 ───
class TestNormalizeFridgeItems:
    def test_basic_normalization(self):
        """基本归一化: 猫名保留, 修饰前缀去除"""
        result = FuzzyMatcher.normalize_fridge_items([
            {"name": "鸡蛋", "cat": "肉蛋"}, {"name": "有机西红柿", "cat": "蔬菜"}])
        assert "鸡蛋" in result
        assert "西红柿" in result

    def test_synonym_expansion(self):
        """同义词展开: 冰箱中的"番茄"应自动展开为"西红柿" """
        result = FuzzyMatcher.normalize_fridge_items([{"name": "番茄", "cat": "蔬菜"}])
        assert "西红柿" in result

    def test_empty(self):
        """空冰箱输入返回空集合"""
        assert FuzzyMatcher.normalize_fridge_items([]) == set()


# ─── INGREDIENT_SYNONYMS 数据完整性 — 对称性 + 无自引用 ───
class TestSynonyms:
    def test_symmetry(self):
        """同义词字典对称性: 每个 key→value 都应有对应的 value→key 反向映射"""
        for key, syns in INGREDIENT_SYNONYMS.items():
            for s in syns:
                assert s in INGREDIENT_SYNONYMS, f"非对称: {key}→{s}"
                assert key in INGREDIENT_SYNONYMS[s], f"非对称: {s}→{key}"

    def test_no_self_reference(self):
        """无自引用: 同义词列表中不应包含自身"""
        for key, syns in INGREDIENT_SYNONYMS.items():
            assert key not in syns, f"自引用: {key}"