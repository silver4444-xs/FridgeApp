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

INGREDIENT_SYNONYMS = {
    '番茄': ['西红柿'],
    '西红柿': ['番茄'],
    '土豆': ['马铃薯', '洋芋'],
    '马铃薯': ['土豆', '洋芋'],
    '西兰花': ['花椰菜', '青花菜'],
    '花椰菜': ['西兰花'],
    '青花菜': ['西兰花'],
    '鸡蛋': ['蛋', '鸡子'],
    '鸡胸肉': ['鸡胸', '鸡脯肉'],
    '鸡胸': ['鸡胸肉'],
    '鸡脯肉': ['鸡胸肉'],
    '猪肉': ['猪', '五花肉'],
    '牛肉': ['牛腩', '牛排'],
    '洋葱': ['洋葱头', '圆葱'],
    '大蒜': ['蒜', '蒜头'],
    '姜': ['生姜', '姜片'],
    '酱油': ['生抽', '老抽'],
    '糖': ['白糖', '细砂糖', '冰糖'],
    '米饭': ['米', '大米', '剩饭'],
    '豆腐': ['嫩豆腐', '老豆腐'],
    '胡萝卜': ['红萝卜'],
    '生菜': ['叶生菜'],
    '三文鱼': ['鲑鱼', '三文鱼排'],
    '黄油': ['牛油'],
    '蜂蜜': ['蜜糖'],
    '牛奶': ['鲜牛奶', '纯牛奶', '鲜奶'],
    '酸奶': ['希腊酸奶', '优格', '酸牛奶'],
    '苹果': ['红富士苹果'],
    '黑胡椒': ['黑胡椒粉', '胡椒'],
    '橄榄油': ['食用油', '植物油'],
    '淀粉': ['生粉', '玉米淀粉', '太白粉'],
    '料酒': ['黄酒', '绍酒', '花雕酒'],
    '辣椒': ['干辣椒', '小米椒', '红辣椒'],
    '青椒': ['青辣椒', '柿子椒', '灯笼椒'],
    '醋': ['白醋', '陈醋', '香醋'],
    '虾': ['大虾', '鲜虾', '虾仁'],
    '鸡肉': ['鸡', '鸡腿肉', '鸡翅'],
    '排骨': ['猪排骨', '肋排'],
    '花生': ['花生米'],
    '黄瓜': ['青瓜'],
    '洋芋': ['土豆', '马铃薯'],
    '蛋': ['鸡蛋'],
    '鸡子': ['鸡蛋'],
    '猪': ['猪肉'],
    '五花肉': ['猪肉'],
    '牛腩': ['牛肉'],
    '牛排': ['牛肉'],
    '洋葱头': ['洋葱'],
    '圆葱': ['洋葱'],
    '蒜': ['大蒜'],
    '蒜头': ['大蒜'],
    '生姜': ['姜'],
    '姜片': ['姜'],
    '生抽': ['酱油'],
    '老抽': ['酱油'],
    '白糖': ['糖'],
    '细砂糖': ['糖'],
    '冰糖': ['糖'],
    '米': ['米饭'],
    '大米': ['米饭'],
    '剩饭': ['米饭'],
    '嫩豆腐': ['豆腐'],
    '老豆腐': ['豆腐'],
    '红萝卜': ['胡萝卜'],
    '叶生菜': ['生菜'],
    '鲑鱼': ['三文鱼'],
    '三文鱼排': ['三文鱼'],
    '牛油': ['黄油'],
    '蜜糖': ['蜂蜜'],
    '鲜牛奶': ['牛奶'],
    '纯牛奶': ['牛奶'],
    '鲜奶': ['牛奶'],
    '希腊酸奶': ['酸奶'],
    '优格': ['酸奶'],
    '酸牛奶': ['酸奶'],
    '红富士苹果': ['苹果'],
    '黑胡椒粉': ['黑胡椒'],
    '胡椒': ['黑胡椒'],
    '食用油': ['橄榄油'],
    '植物油': ['橄榄油'],
    '生粉': ['淀粉'],
    '玉米淀粉': ['淀粉'],
    '太白粉': ['淀粉'],
    '黄酒': ['料酒'],
    '绍酒': ['料酒'],
    '花雕酒': ['料酒'],
    '干辣椒': ['辣椒'],
    '小米椒': ['辣椒'],
    '红辣椒': ['辣椒'],
    '青辣椒': ['青椒'],
    '柿子椒': ['青椒'],
    '灯笼椒': ['青椒'],
    '白醋': ['醋'],
    '陈醋': ['醋'],
    '香醋': ['醋'],
    '大虾': ['虾'],
    '鲜虾': ['虾'],
    '虾仁': ['虾'],
    '鸡': ['鸡肉'],
    '鸡腿肉': ['鸡肉'],
    '鸡翅': ['鸡肉'],
    '猪排骨': ['排骨'],
    '肋排': ['排骨'],
    '花生米': ['花生'],
    '青瓜': ['黄瓜'],
}


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
        n = re.sub(r'\d+[g克千k][克g]?$', '', n)
        n = re.sub(r'\d+m[lL]$', '', n)
        for u in sorted(UNIT_SUFFIXES, key=len, reverse=True):
            if n.endswith(u) and len(n) > len(u) and n[-len(u)-1].isdigit():
                n = n[:-len(u)]
                break
        n = re.sub(r'\d+$', '', n)
        return n.strip().lower()

    @staticmethod
    def is_match(ingredient: Dict, fridge_names: Set[str]) -> bool:
        candidates = {FuzzyMatcher.normalize(ingredient["name"])}
        for a in ingredient.get("aliases", []):
            candidates.add(FuzzyMatcher.normalize(a))
        for c in list(candidates):
            for syn in INGREDIENT_SYNONYMS.get(c, []):
                candidates.add(syn)
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
        expanded = set(names)
        for name in names:
            for syn in INGREDIENT_SYNONYMS.get(name, []):
                expanded.add(syn)
        return expanded
