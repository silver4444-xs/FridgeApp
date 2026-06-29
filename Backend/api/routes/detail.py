"""
GET /api/recipes/{id} — 菜谱详情
"""
from fastapi import APIRouter, Depends, HTTPException
from ..models import RecipeDetail
from ..dependencies import get_recipe_db
from matching.recipe_database import RecipeDatabase

router = APIRouter()


@router.get("/{recipe_id}", response_model=RecipeDetail)
def get_recipe(recipe_id: str, db: RecipeDatabase = Depends(get_recipe_db)):
    recipe = db.get(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    return RecipeDetail(
        id=recipe["id"],
        name=recipe["name"],
        image=recipe.get("image"),
        category=recipe.get("category", "其他"),
        difficulty=recipe.get("difficulty", "未知"),
        time=recipe.get("time", "未知"),
        ingredients=recipe.get("ingredients", []),
        steps=recipe.get("steps", []),
        tips=recipe.get("tips", ""),
        tags=recipe.get("tags", []),
        source=recipe.get("source", ""),
    )
