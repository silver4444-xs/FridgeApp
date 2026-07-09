"""
模糊匹配器 — 食材名归一化与别名匹配
被 inverted_index.py 和 recommend.py 调用
"""
import re
from typing import List, Set, Dict

MODIFIER_PREFIXES = [
    '有机', '鲜', '澳洲', '红富士', '希腊', '进口', '土', '纯', '精品',
    '新鲜', '精选', '特级', '一级', '绿色', '无公害', '生态', '散养',
]

UNIT_SUFFIXES = ['g', 'kg', 'ml', 'l', '颗', '个', '瓶', '盒', '袋', '根', '把', '斤', '两']


class FuzzyMatcher:

    @staticmethod
    def normalize(name: str) -> str:
        n = name.strip()
        changed = True
        while changed:
            changed = False
            for prefix in sorted(MODIFIER_PREFIXES, key=len, reverse=True):
                if n.startswith(prefix) and len(n) > len(prefix):
                    n = n[len(prefix):]
                    changed = True
                    break
        n = re.sub(r'\d+$', '', n)
        n = re.sub(r'\d+[g克千k][克g]?$', '', n)
        n = re.sub(r'\d+m[lL]$', '', n)
        for u in UNIT_SUFFIXES:
            if n.endswith(u):
                n = n[:-len(u)]
                break
        return n.strip().lower()

    @staticmethod
    def is_match(ingredient: Dict, fridge_names: Set[str]) -> bool:
        candidates = {FuzzyMatcher.normalize(ingredient["name"])}
        for a in ingredient.get("aliases", []):
            candidates.add(FuzzyMatcher.normalize(a))
        candidates.discard('')

        if candidates & fridge_names:
            return True

        for c in candidates:
            for fn in fridge_names:
                if fn and (c in fn or fn in c):
                    return True
        return False

    @staticmethod
    def normalize_fridge_items(items: List[Dict]) -> Set[str]:
        names = set()
        for item in items:
            n = FuzzyMatcher.normalize(item.get("name", ""))
            if n: names.add(n)
            raw = item.get("name", "").strip().lower()
            if raw: names.add(raw)
        return names
