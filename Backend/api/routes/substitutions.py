"""
POST /api/recipes/{id}/suggest-substitutions — LLM 食材替换建议
"""
from fastapi import APIRouter, Depends, HTTPException
from ..models import SubstitutionRequest, SubstitutionResponse
from ..dependencies import get_recipe_db, get_rag_system
from matching.recipe_database import RecipeDatabase

router = APIRouter()


@router.post("/{recipe_id}/suggest-substitutions", response_model=SubstitutionResponse)
def suggest(recipe_id: str,
            req: SubstitutionRequest,
            db: RecipeDatabase = Depends(get_recipe_db)):
    recipe = db.get(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    rag = get_rag_system()
    if not rag or not rag.generation_module:
        return SubstitutionResponse(
            substitutions=[
                {"missing": ing, "suggestion": f"{ing} 可在超市购买或尝试省略", "feasibility": "unknown"}
                for ing in req.missing_ingredients
            ],
            summary="（LLM 未初始化，无法生成智能替换建议）"
        )

    prompt = f"""你是一位专业厨师。用户想做"{recipe['name']}"，但缺少以下食材:
{chr(10).join(f'- {i}' for i in req.missing_ingredients)}

用户冰箱里现有食材:
{chr(10).join(f'- {i}' for i in req.available_ingredients)}

请为每个缺少的食材建议可能的替换方案。"""
    try:
        response = rag.generation_module.generate_adaptive_answer(prompt, [])
        return SubstitutionResponse(
            substitutions=[
                {"ingredient": ing, "suggestion": "见下方 summary", "feasibility": "unknown"}
                for ing in req.missing_ingredients
            ],
            summary=response,
        )
    except Exception as e:
        return SubstitutionResponse(substitutions=[], summary="生成建议失败: {}".format(e))
