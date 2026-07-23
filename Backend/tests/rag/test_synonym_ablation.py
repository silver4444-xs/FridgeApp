"""
同义词三层覆盖消融实验 (P2-2)

逐层剥离三层同义词策略，测量每层对 Recall@K 的独立贡献。

配置对比:
  基线:     Layer1(索引展开) + Layer2(搜索展开) + Layer3(子串) + 归一化
  剥离子串:  Layer1 + Layer2 + 归一化
  剥离搜索:  Layer1 + 归一化
  剥离索引:  仅归一化
  剥离归一化: 原始食材名

用法: pytest tests/rag/test_synonym_ablation.py -v -m rag -s
"""
import random
import pytest
from matching.fuzzy_matcher import FuzzyMatcher, INGREDIENT_SYNONYMS


def _load_eval_queries():
    """从菜谱数据库生成查询集：每道菜谱随机取 1 个食材名作为查询词。"""
    from api.dependencies import recipe_db
    random.seed(42)
    queries = []
    for rid in list(recipe_db._recipes.keys()):
        recipe = recipe_db.get(rid)
        if not recipe:
            continue
        ings = recipe.get("ingredients", [])
        if not ings:
            continue
        ing = random.choice(ings)
        queries.append({
            "query": ing["name"],
            "recipe_id": rid,
            "recipe_name": recipe.get("name", ""),
        })
    return queries


def _run_config(queries, layers, inverted_index):
    """在指定层配置下计算 Recall@K。"""
    k_vals = [5, 10]
    hits = {k: 0 for k in k_vals}
    idx = getattr(inverted_index, '_index', {})

    for q in queries:
        name = q["query"]
        # 归一化
        if layers.get("normalize", True):
            norm = FuzzyMatcher.normalize_fridge_items(
                [{"name": name, "cat": "packaged"}])
            search_keys = list(norm)
        else:
            search_keys = [name]

        # 搜索时同义词展开
        if layers.get("layer2_expand_search", True):
            expanded = list(search_keys)
            for n in search_keys:
                for syn in INGREDIENT_SYNONYMS.get(n, []):
                    expanded.append(syn)
            search_keys = expanded

        # 索引查找
        results = set()
        if layers.get("layer1_expand_idx", True):
            results = set(inverted_index.fuzzy_lookup(search_keys))
        else:
            for key in search_keys:
                if key in idx:
                    results.update(idx[key])

        # 子串兜底
        if not layers.get("layer3_substring", True):
            exact = set()
            for key in search_keys:
                if key in idx:
                    exact.update(idx[key])
            results = exact

        for k in k_vals:
            if q["recipe_id"] in list(results)[:k]:
                hits[k] += 1

    n = len(queries)
    return {f"recall@{k}": hits[k] / n if n else 0.0 for k in k_vals}


class TestSynonymAblation:
    """逐层剥离测量同义词覆盖率贡献。"""

    @pytest.mark.rag
    def test_ablation(self, init_rag_system):
        queries = _load_eval_queries()
        if len(queries) < 50:
            pytest.skip(f"查询集 {len(queries)} 条，至少需要 50")

        from api.dependencies import inverted_index

        configs = {
            "基线(三层全部)":       {"L1": True,  "L2": True,  "L3": True,  "norm": True},
            "剥离L3(子串)":        {"L1": True,  "L2": True,  "L3": False, "norm": True},
            "剥离L2+3(搜索+子串)":  {"L1": True,  "L2": False, "L3": False, "norm": True},
            "剥离L1+2+3(仅归一化)": {"L1": False, "L2": False, "L3": False, "norm": True},
            "无归一化":            {"L1": False, "L2": False, "L3": False, "norm": False},
        }

        results = {}
        print(f"\n{'='*60}\n  同义词消融实验 ({len(queries)} 查询)\n{'='*60}")
        print(f"  {'配置':<30s} {'Recall@5':>8s} {'Recall@10':>8s}")
        print("-" * 48)

        for name, cfg in configs.items():
            layers = {
                "layer1_expand_idx": cfg["L1"],
                "layer2_expand_search": cfg["L2"],
                "layer3_substring": cfg["L3"],
                "normalize": cfg["norm"],
            }
            s = _run_config(queries, layers, inverted_index)
            results[name] = s
            print(f"  {name:<30s} {s['recall@5']:>8.4f} {s['recall@10']:>8.4f}")

        b = results["基线(三层全部)"]
        no3 = results["剥离L3(子串)"]
        no23 = results["剥离L2+3(搜索+子串)"]
        no123 = results["剥离L1+2+3(仅归一化)"]
        nonorm = results["无归一化"]

        print("-" * 48)
        print(f"  Layer3(子串)贡献:     {b['recall@5'] - no3['recall@5']:>+8.4f}")
        print(f"  Layer2(搜索展开)贡献:  {no3['recall@5'] - no23['recall@5']:>+8.4f}")
        print(f"  Layer1(索引展开)贡献:  {no23['recall@5'] - no123['recall@5']:>+8.4f}")
        print(f"  归一化贡献:            {no123['recall@5'] - nonorm['recall@5']:>+8.4f}")
        print("=" * 60)

        assert b["recall@5"] >= nonorm["recall@5"], "三层覆盖应不低于无归一化"
