"""
GET /api/recipes/search?q=xxx — 菜谱名称搜索 (基于字符索引)
"""
from fastapi import APIRouter, Depends, Query
from ..dependencies import get_recipe_db
from matching.recipe_database import RecipeDatabase

router = APIRouter()


@router.get("/search")
def search(q: str = Query(..., min_length=1),
           limit: int = Query(default=20, ge=1, le=50),
           db: RecipeDatabase = Depends(get_recipe_db)):
    matched_ids = db.search_names(q)
    results = []
    for rid in matched_ids[:limit]:
        recipe = db.get(rid)
        if not recipe:
            continue
        results.append({
            "id": recipe["id"],
            "name": recipe["name"],
            "category": recipe.get("category", ""),
            "difficulty": recipe.get("difficulty", ""),
            "time": recipe.get("time", ""),
            "image": recipe.get("image"),
            "ingredients": [i["name"] if isinstance(i, dict) else str(i) for i in recipe.get("ingredients", [])],
            "steps": recipe.get("steps", []),
            "tags": recipe.get("tags", []),
        })
    return {"results": results, "query": q}
