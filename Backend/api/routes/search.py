"""
GET /api/recipes/search?q=xxx — 菜谱名称精准搜索
"""
from fastapi import APIRouter, Depends, Query
from ..dependencies import get_recipe_db
from matching.recipe_database import RecipeDatabase

router = APIRouter()


def match_score(name: str, query: str) -> int:
    n, q = name.replace(' ', ''), query.replace(' ', '')
    if n == q:
        return 1000
    if n.startswith(q):
        return 900
    if q in n:
        return 800
    # 逐字匹配 + 顺序加分
    chars = set(q)
    matched = sum(1 for c in chars if c in n)
    if matched < max(2, len(q) // 2 + 1):
        return 0
    # 连续子序列加分
    bonus = 0
    for i in range(len(q) - 1):
        pair = q[i:i + 2]
        if pair in n:
            bonus += 100
    return matched * 20 + bonus


@router.get("/search")
def search(q: str = Query(..., min_length=1),
           limit: int = Query(default=20, ge=1, le=50),
           db: RecipeDatabase = Depends(get_recipe_db)):
    results = []
    for recipe in db.all():
        score = match_score(recipe["name"], q)
        if score > 0:
            r = {
                "id": recipe["id"],
                "name": recipe["name"],
                "category": recipe.get("category", ""),
                "difficulty": recipe.get("difficulty", ""),
                "time": recipe.get("time", ""),
                "image": recipe.get("image"),
                "ingredients": [i["name"] if isinstance(i, dict) else str(i) for i in recipe.get("ingredients", [])],
                "steps": recipe.get("steps", []),
                "tags": recipe.get("tags", []),
                "_score": score,
            }
            results.append(r)

    results.sort(key=lambda r: r["_score"], reverse=True)
    for r in results:
        del r["_score"]

    return {"results": results[:limit], "query": q}
