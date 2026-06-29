"""
POST /api/recipes/recommend — 核心推荐接口
"""
import time
import logging
from fastapi import APIRouter, Depends
from ..models import RecommendRequest, RecommendResponse, RecipeSummary, RecommendMeta
from ..dependencies import get_recipe_db, get_inverted_index
from matching.fuzzy_matcher import FuzzyMatcher
from matching.recipe_database import RecipeDatabase
from matching.inverted_index import InvertedIndex

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse)
def recommend(req: RecommendRequest,
              db: RecipeDatabase = Depends(get_recipe_db),
              idx: InvertedIndex = Depends(get_inverted_index)):
    t0 = time.time()

    fridge_names = FuzzyMatcher.normalize_fridge_items(
        [{"name": ing.name, "cat": ing.cat} for ing in req.ingredients]
    )

    candidate_ids = idx.fuzzy_lookup(fridge_names)

    results = []
    for rid in candidate_ids:
        recipe = db.get(rid)
        if not recipe:
            continue

        matched = []
        missing = []
        for ing in recipe.get("ingredients", []):
            if FuzzyMatcher.is_match(ing, fridge_names):
                matched.append(ing["name"])
            elif ing.get("required", True):
                missing.append(ing["name"])

        match_count = len(matched)
        if match_count < req.min_match:
            continue

        total = len([i for i in recipe.get("ingredients", []) if i.get("required", True)])
        ratio = match_count / total if total > 0 else 0

        results.append(RecipeSummary(
            id=recipe["id"],
            name=recipe["name"],
            image=recipe.get("image"),
            category=recipe.get("category", "其他"),
            difficulty=recipe.get("difficulty", "未知"),
            time=recipe.get("time", "未知"),
            ingredients=[i["name"] for i in recipe.get("ingredients", [])],
            matchCount=match_count,
            totalIngredients=total,
            matchRatio=round(ratio, 2),
            ownedIngredients=matched,
            missingIngredients=missing,
            steps=recipe.get("steps", []),
            tags=recipe.get("tags", []),
        ))

    results.sort(key=lambda r: (r.matchCount, r.matchRatio), reverse=True)
    results = results[:req.limit]

    elapsed = int((time.time() - t0) * 1000)
    logger.info(f"推荐完成: {len(results)} 道菜谱, 耗时 {elapsed}ms")

    return RecommendResponse(
        recipes=results,
        meta=RecommendMeta(
            total_matched=len(results),
            fridge_items_count=len(req.ingredients),
        )
    )
