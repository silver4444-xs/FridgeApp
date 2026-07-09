"""
菜谱数据库 — 中央注册表，内存常驻
被 api/server.py 和 api/routes/* 调用
"""
import logging
from pathlib import Path
from typing import List, Dict, Optional

from .ingredient_extractor import IngredientExtractor

logger = logging.getLogger(__name__)


class RecipeDatabase:

    def __init__(self):
        self._recipes: Dict[str, Dict] = {}
        self._name_index: Dict[str, set] = {}

    def build_from_documents(self, documents: List):
        self._recipes.clear()
        self._name_index.clear()
        for doc in documents:
            meta = doc.metadata
            rid = meta.get("parent_id", "")
            if not rid:
                continue

            extracted = IngredientExtractor.extract(doc.page_content)
            image = self._find_image(meta.get("source", ""))
            tags = self._generate_tags(meta.get("category", ""), doc.page_content)

            name = meta.get("dish_name", "未知菜品")
            self._recipes[rid] = {
                "id": rid,
                "name": name,
                "category": meta.get("category", "其他"),
                "difficulty": meta.get("difficulty", "未知"),
                "time": extracted["time"],
                "image": image,
                "ingredients": extracted["ingredients"],
                "steps": extracted["steps"],
                "tips": extracted["tips"],
                "tags": tags,
                "source": meta.get("source", ""),
            }
            self._build_name_index(rid, name)

        logger.info(f"菜谱数据库构建完成: {len(self._recipes)} 道菜谱")

    def get(self, recipe_id: str) -> Optional[Dict]:
        return self._recipes.get(recipe_id)

    def all(self) -> List[Dict]:
        return list(self._recipes.values())

    def __len__(self):
        return len(self._recipes)

    def _build_name_index(self, rid: str, name: str):
        for ch in name:
            if ch not in self._name_index:
                self._name_index[ch] = set()
            self._name_index[ch].add(rid)

    def search_names(self, query: str) -> List[str]:
        """按菜名搜索，返回匹配的 recipe_id 列表（按相关性排序）。"""
        if not query:
            return []
        q = query.replace(' ', '')
        # 用第一个字符缩小候选集
        candidates = set(self._recipes.keys())
        if q and q[0] in self._name_index:
            candidates = self._name_index[q[0]]
        results = []
        for rid in candidates:
            name = self._recipes[rid]["name"].replace(' ', '')
            if q in name:
                # 评分: 完全匹配 > 前缀匹配 > 包含匹配 > 部分字符匹配
                if name == q:
                    score = 1000
                elif name.startswith(q):
                    score = 900
                else:
                    score = 800
                results.append((rid, score))
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results]

    def _find_image(self, source_path: str) -> Optional[str]:
        if not source_path:
            return None
        try:
            parent = Path(source_path).parent
            for ext in ('.jpg', '.jpeg', '.png', '.webp'):
                for f in parent.glob(f'*{ext}'):
                    return str(f)
        except Exception:
            pass
        return None

    def _generate_tags(self, category: str, content: str) -> List[str]:
        tags = []
        if category:
            tags.append(category)
        kw_map = {
            '炖': '炖煮', '炒': '快炒', '蒸': '清蒸', '烤': '烘烤',
            '煎': '煎烤', '炸': '油炸', '凉拌': '凉拌', '拌': '凉拌',
            '汤': '汤品', '煲': '煲煮', '红烧': '红烧',
        }
        for kw, tag in kw_map.items():
            if kw in content and tag not in tags:
                tags.append(tag)
        if '★' in content:
            stars = content.count('★')
            if stars <= 2:
                tags.append('快手')
            elif stars >= 4:
                tags.append('硬菜')
        return tags[:5]
