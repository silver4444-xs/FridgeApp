"""
AI 增强评测数据集生成脚本。

从金标集 + 菜谱数据库种子出发, 用结构化 prompt (含 Few-shot 金标示例)
让 DeepSeek 批量生成评测数据。配合 cross_validate_qwen.py 质控。

用法:
  cd Backend
  python tests/rag/scripts/generate_enhanced_dataset.py --num-seeds 80
"""

import json
import os
import re
import sys
import random
import argparse
from pathlib import Path
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import httpx
from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.schema import HumanMessage, SystemMessage

GENERATION_SYSTEM_PROMPT = """你是一个烹饪领域评测数据生成专家。你的任务是生成 RAG 系统评测用的问题-答案对。

## 核心约束
1. 基于提供的 [菜谱内容/食材知识] 种子来构造问题，问题的答案必须在提供的内容中可找到
2. reference_contexts 只填真实存在的文件路径（我会在种子信息中提供）
3. ground_truth 严格基于提供的上下文整理，不编造、不推测
4. 生成的问题要像真实用户会问的方式 —— 口语化、自然
5. 问题长度 8-60 字，答案长度 30-300 字

## 多样性要求
- 覆盖三种难度: easy (简单事实查询) / medium (需要理解或比较) / hard (跨领域或边界情况)
- 覆盖多种类别: cooking_technique, recipe_detail, ingredient_knowledge, ingredient_pairing,
  cuisine_knowledge, substitution, recipe_recommendation, food_safety, kitchen_equipment, beginner_friendly

## Few-shot 示例

以下是高质量评测数据的示例:

示例 1 (easy, recipe_detail):
输入种子: 菜谱"番茄炒蛋"，食材: 鸡蛋、番茄
输出:
```json
{
  "question": "番茄炒蛋需要哪些食材？",
  "ground_truth": "鸡蛋、番茄、葱、盐、糖、食用油",
  "reference_contexts": ["data/dishes/vegetarian/番茄炒蛋.md"],
  "category": "recipe_detail",
  "difficulty": "easy"
}
```

示例 2 (medium, cooking_technique):
输入种子: 菜谱"红烧肉"，食材: 五花肉、冰糖
输出:
```json
{
  "question": "做红烧肉炒糖色总是失败，有什么技巧？",
  "ground_truth": "用水炒法更容易控制: 锅中放少量水和冰糖，小火慢熬，从大泡变小泡、颜色从白到黄再到琥珀色时立即关火加入热水。全程小火、不停搅拌",
  "reference_contexts": ["data/dishes/pork/红烧肉.md"],
  "category": "cooking_technique",
  "difficulty": "medium"
}
```

示例 3 (easy, recipe_recommendation):
输入种子: 食材"鸡蛋、番茄、剩米饭"
输出:
```json
{
  "question": "冰箱里只有鸡蛋、番茄和剩米饭，能做什么？",
  "ground_truth": "可以做番茄鸡蛋炒饭: 鸡蛋打散炒熟盛出，番茄切块炒出汁，加入米饭炒散，加入鸡蛋和调料翻炒均匀即可",
  "reference_contexts": ["data/dishes/rice_noodles/蛋炒饭.md"],
  "category": "recipe_recommendation",
  "difficulty": "easy"
}
```

## 输出格式
对每个种子，输出一个 JSON 对象，包含 question, ground_truth, reference_contexts, category, difficulty。
只输出 JSON 对象，不要添加额外的解释文字。"""


def _extract_json_objects(text: str) -> List[Dict]:
    """从 LLM 输出中提取 JSON 对象列表。"""
    results = []
    text = re.sub(r'```json\s*', '', text)
    text = re.sub(r'```\s*', '', text)
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i+1]
                try:
                    obj = json.loads(candidate)
                    if "question" in obj and "ground_truth" in obj:
                        results.append(obj)
                except json.JSONDecodeError:
                    pass
                start = None
    return results


def get_seed_data() -> List[Dict]:
    """从菜谱数据库提取种子数据。"""
    import api.dependencies as deps
    seeds = []
    for rid, recipe in deps.recipe_db._recipes.items():
        content_parts = []
        if recipe.get("ingredients"):
            content_parts.append(f"食材: {recipe['ingredients']}")
        if recipe.get("steps"):
            content_parts.append(f"步骤: {recipe['steps']}")
        if recipe.get("tips"):
            content_parts.append(f"技巧: {recipe['tips']}")
        seeds.append({
            "entity": recipe.get("name", "未知菜品"),
            "content": "\n".join(content_parts),
            "file_path": recipe.get("source", ""),
        })
    return seeds


def build_generation_prompt(seed: Dict) -> str:
    """构造单条种子对应的生成 prompt。"""
    return f"""请基于以下种子信息生成 2 条评测数据:

种子实体: {seed['entity']}
文件路径: {seed['file_path']}
知识内容:
---
{seed['content'][:2000]}
---

请生成 2 条不同难度和类别的评测数据。每条数据输出一个 JSON 对象。
确保 question 口语化、ground_truth 基于提供的内容、reference_contexts 只包含 {seed['file_path']}。"""


def generate_candidates(
    seeds: List[Dict],
    model_name: str = "deepseek-v4-flash",
    api_key: str = None,
    api_base: str = "https://api.deepseek.com/v1",
    temperature: float = 0.3,
) -> List[Dict]:
    """批量生成评测数据候选集。"""
    api_key = api_key or os.getenv("EVAL_API_KEY")
    if not api_key:
        raise ValueError("EVAL_API_KEY 未设置")

    llm = init_chat_model(
        f"openai:{model_name}",
        temperature=temperature, max_tokens=4096,
        openai_api_key=api_key, openai_api_base=api_base,
        http_client=httpx.Client(timeout=httpx.Timeout(connect=10, read=120, write=10, pool=10)))

    candidates = []
    for i, seed in enumerate(seeds):
        prompt = build_generation_prompt(seed)
        messages = [
            SystemMessage(content=GENERATION_SYSTEM_PROMPT),
            HumanMessage(content=prompt),
        ]
        try:
            response = llm.invoke(messages)
            text = response.content if hasattr(response, 'content') else str(response)
            items = _extract_json_objects(text)
            for item in items:
                item["annotated_by"] = "AI-enhanced"
                item["verified_against_kb"] = False
                item["annotated_at"] = "2026-08-02"
                item["seed_entity"] = seed["entity"]
            candidates.extend(items)
            print(f"  [{i+1}/{len(seeds)}] {seed['entity']}: 生成 {len(items)} 条")
        except Exception as e:
            print(f"  [{i+1}/{len(seeds)}] {seed['entity']}: 失败 - {e}")

    print(f"\n共生成 {len(candidates)} 条候选")
    return candidates


def run_quality_checks(items: List[Dict], golden_dataset_path: str = None) -> List[Dict]:
    """自动质控过滤: 去重/过滤空/过短/全英文/与金标集去重。"""
    passed = []
    stats = {"empty_gt": 0, "short_gt": 0, "empty_q": 0, "english": 0, "duplicate": 0}

    golden_questions = set()
    if golden_dataset_path:
        golden_path = Path(golden_dataset_path)
        if golden_path.exists():
            with open(golden_path, encoding="utf-8") as f:
                golden_items = json.load(f)
                golden_questions = {item["question"] for item in golden_items}

    for item in items:
        gt = item.get("ground_truth", "")
        q = item.get("question", "")
        if not gt:
            stats["empty_gt"] += 1; continue
        if len(gt) < 30:
            stats["short_gt"] += 1; continue
        if not q or len(q) < 5 or len(q) > 100:
            stats["empty_q"] += 1; continue
        if q in golden_questions:
            stats["duplicate"] += 1; continue
        chinese_chars = len(re.findall(r'[一-鿿]', q))
        if chinese_chars == 0:
            stats["english"] += 1; continue
        item["verified_against_kb"] = False
        passed.append(item)

    print(f"\n自动质控完成:")
    print(f"  输入: {len(items)} 条")
    print(f"  通过: {len(passed)} 条")
    print(f"  过滤: empty_gt={stats['empty_gt']}, short_gt={stats['short_gt']}, "
          f"empty_q={stats['empty_q']}, english={stats['english']}, duplicate={stats['duplicate']}")
    return passed


def generate_and_validate(
    output_path: str,
    num_seeds: int = 80,
    qwen_api_key: str = None,
    golden_dataset_path: str = None,
):
    """完整的生成+质控流水线: 种子→生成→质控→交叉验证→输出。"""
    from cross_validate_qwen import cross_validate_with_qwen

    print("=" * 50)
    print("Step 1: 从菜谱数据库获取种子")
    print("=" * 50)
    all_seeds = get_seed_data()
    seeds = random.sample(all_seeds, min(num_seeds, len(all_seeds)))
    print(f"从 {len(all_seeds)} 道菜谱中随机选取 {len(seeds)} 个种子")

    print("\n" + "=" * 50)
    print("Step 2: DeepSeek 批量生成候选")
    print("=" * 50)
    candidates = generate_candidates(seeds, temperature=0.3)

    print("\n" + "=" * 50)
    print("Step 3: 自动质控")
    print("=" * 50)
    if golden_dataset_path is None:
        golden_dataset_path = str(
            Path(__file__).resolve().parent.parent / "eval_data" / "golden_dataset.json")
    passed = run_quality_checks(candidates, golden_dataset_path)

    print("\n" + "=" * 50)
    print("Step 4: 千问交叉验证")
    print("=" * 50)
    scored = cross_validate_with_qwen(passed, api_key=qwen_api_key)

    final = []
    for item, score in scored:
        if score >= 4.0:
            item["qwen_score"] = score
            item["verified_against_kb"] = True
            final.append(item)

    print(f"\n最终通过: {len(final)} 条 (score >= 4.0)")

    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)

    print(f"完成! 共生成 {len(final)} 条 AI 增强评测数据 → {output_path}")
    return final


if __name__ == "__main__":
    load_dotenv(Path(__file__).resolve().parents[3] / ".env.test")

    parser = argparse.ArgumentParser(description="AI 增强评测数据集生成")
    parser.add_argument("--output", default=None, help="输出文件路径")
    parser.add_argument("--num-seeds", type=int, default=80, help="种子数量")
    parser.add_argument("--qwen-key", default=None, help="千问 API Key")
    args = parser.parse_args()

    output = args.output or str(
        Path(__file__).resolve().parent.parent / "eval_data" / "enhanced_dataset.json")

    generate_and_validate(
        output_path=output,
        num_seeds=args.num_seeds,
        qwen_api_key=args.qwen_key,
    )
