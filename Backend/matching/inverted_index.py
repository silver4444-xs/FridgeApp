"""
倒排索引 — 食材→菜谱 O(1) 查找
被 api/routes/recommend.py 调用
"""
import logging
from collections import defaultdict
from typing import List, Set, Dict

from .fuzzy_matcher import FuzzyMatcher

logger = logging.getLogger(__name__)


class InvertedIndex:

    def __init__(self):
        self._index: Dict[str, Set[str]] = defaultdict(set)

    def build(self, recipes: List[Dict]):
        self._index.clear()
        for recipe in recipes:
            rid = recipe["id"]
            for ing in recipe.get("ingredients", []):
                names = {FuzzyMatcher.normalize(ing["name"])}
                for a in ing.get("aliases", []):
                    names.add(FuzzyMatcher.normalize(a))
                for n in names:
                    if n:
                        self._index[n].add(rid)
        logger.info(f"倒排索引构建完成: {len(self._index)} 个食材词条, {len(recipes)} 道菜谱")

    def lookup(self, ingredient_name: str) -> Set[str]:
        n = FuzzyMatcher.normalize(ingredient_name)
        return self._index.get(n, set())

    def fuzzy_lookup(self, fridge_names: Set[str]) -> Set[str]:
        result_ids = set()
        for fname in fridge_names:
            if not fname:
                continue
            ids = self._index.get(fname, set())
            result_ids.update(ids)
            for key, rids in self._index.items():
                if fname in key or key in fname:
                    result_ids.update(rids)
        return result_ids

    def __len__(self):
        return len(self._index)
