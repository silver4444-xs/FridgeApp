"""InvertedIndex — 食材→菜谱 O(1) 倒排索引: 构建/精确查找/模糊查找/同义词"""
import pytest
from matching.inverted_index import InvertedIndex


# ─── 倒排索引完整功能: build → lookup/fuzzy_lookup → 同义词感知 ───
class TestInvertedIndex:
    # ── 精确查找 (lookup) ──
    def test_build_and_lookup(self, sample_recipes):
        """构建索引后精确查找: "鸡蛋" 应命中 r001 和 r003, 不应命中 r002"""
        idx = InvertedIndex(); idx.build(sample_recipes)
        result = idx.lookup("鸡蛋")
        assert "r001" in result and "r003" in result
        assert "r002" not in result

    def test_lookup_nonexistent(self, sample_recipes):
        """查找不存在的食材返回空集合"""
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert idx.lookup("不存在食材") == set()

    # ── 模糊查找 (fuzzy_lookup) — 归一化 + 同义词 + 子串 ──
    def test_fuzzy_lookup(self, sample_recipes):
        """模糊查找: 输入归一化后的食材名集合, 返回所有匹配菜谱ID"""
        idx = InvertedIndex(); idx.build(sample_recipes)
        result = idx.fuzzy_lookup({"鸡蛋", "鸡胸肉"})
        assert result == {"r001", "r002", "r003"}

    def test_fuzzy_lookup_substring(self, sample_recipes):
        """模糊查找子串匹配: "鸡胸" 作为子串应命中含"鸡胸肉"的菜谱"""
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert "r002" in idx.fuzzy_lookup({"鸡胸"})

    def test_fuzzy_lookup_empty(self, sample_recipes):
        """空输入模糊查找返回空集合"""
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert idx.fuzzy_lookup(set()) == set()

    # ── 同义词感知 — 构建时自动展开 ──
    def test_synonym_during_build(self):
        """构建索引时自动展开同义词: 菜谱含"番茄", 用"西红柿"搜索也应命中"""
        recipes = [{"id": "t1", "name": "t", "ingredients": [{"name": "番茄"}]}]
        idx = InvertedIndex(); idx.build(recipes)
        assert "t1" in idx.fuzzy_lookup({"西红柿"})

    # ── 索引元信息 ──
    def test_len(self, sample_recipes):
        """构建后索引长度 > 0"""
        idx = InvertedIndex(); idx.build(sample_recipes)
        assert len(idx) > 0