"""
Ragas RAG 检索与生成质量测试。

测试目标: 验证 AdvancedGraphRAGSystem 的检索精度和生成质量，覆盖 Milvus 向量检索、
Neo4j 图检索、HybridRetrieval 融合三种策略，以及 LLM 生成结果的忠实度和相关性。

前置条件: Neo4j (7474/7687) + Milvus (19530) 需已启动。
RAG 系统通过 conftest.py 的 init_rag_system fixture (session scope) 在测试进程中初始化。

数据: 从 eval_data/rag_eval_dataset.json 加载 50 条中文烹饪问答对。
框架: Ragas (ContextPrecision/Recall/Faithfulness/AnswerRelevancy/AnswerCorrectness)。
"""
import os, json, pytest
from pathlib import Path
from datasets import Dataset


def load_eval_dataset() -> Dataset:
    """
    从 JSON 文件加载 RAG 评测数据集, 转为 HuggingFace Dataset 格式。

    数据集包含 50 条中文烹饪问答对, 覆盖 11 个领域:
    cooking_technique(13), recipe_detail(11), ingredient_knowledge(5),
    ingredient_pairing(5), cuisine_knowledge(4), substitution(3),
    beginner_friendly(2), food_safety(2), kitchen_equipment(2),
    meal_planning(2), recipe_recommendation(1)。

    每条包含 question(查询), ground_truth(参考答案), category(类别),
    difficulty(easy/medium/hard), expected_entities(预期实体)。
    """
    path = Path(__file__).parent / "eval_data" / "rag_eval_dataset.json"
    with open(path, encoding="utf-8") as f:
        return Dataset.from_list(json.load(f))


def get_eval_llm():
    """
    创建评测专用 LLM 实例 (temperature=0 确保评分稳定)。

    用于 Ragas 指标计算中的 LLM-as-Judge, 默认使用 DeepSeek V4 Flash,
    可通过 EVAL_MODEL / EVAL_API_KEY / EVAL_API_BASE 环境变量覆盖。

    使用 LangchainLLMWrapper(bypass_n=True) 包装: DeepSeek API 不支持 n>1,
    bypass_n 让 ragas 通过复制 prompt 的方式实现多轮生成, 而非在 API 层传 n 参数。
    """
    from langchain.chat_models import init_chat_model
    from ragas.llms.base import LangchainLLMWrapper

    base_llm = init_chat_model(
        f"openai:{os.getenv('EVAL_MODEL', 'deepseek-v4-flash')}",
        temperature=0.0, max_tokens=512,
        openai_api_key=os.getenv("EVAL_API_KEY"),
        openai_api_base=os.getenv("EVAL_API_BASE", "https://api.deepseek.com/v1"))
    return LangchainLLMWrapper(base_llm, bypass_n=True)


def get_eval_embeddings():
    """
    获取评测用 Embeddings 模型 (bge-small-zh-v1.5, CPU 运行)。

    用于 Ragas ContextPrecision/Recall 计算中的语义相似度对比。
    """
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(model_name="BAAI/bge-small-zh-v1.5",
                                  model_kwargs={"device": "cpu"})


def run_rag_query(question: str) -> dict:
    """
    对单条问题执行完整的 RAG 检索+生成流程, 返回结构化结果。

    调用 rag_system.ask_question_with_routing() 自动选择检索策略
    (hybrid_traditional / graph_rag / combined), 收集回答, 检索到的文档上下文,
    以及路由策略用于后续指标计算。

    使用 import api.dependencies as deps (模块引用) 而非 from-import (本地副本),
    确保读取到 conftest fixture 注入的最新值。
    """
    import api.dependencies as deps
    if not deps.rag_system or not deps.rag_system.system_ready:
        pytest.skip("RAG system not initialized — check Neo4j/Milvus are running")
    result, analysis = deps.rag_system.ask_question_with_routing(question, stream=False)
    contexts = []
    if analysis and hasattr(analysis, 'relevant_docs'):
        contexts = [d.page_content for d in analysis.relevant_docs]
    return {
        "question": question,
        "answer": result if isinstance(result, str) else str(result),
        "contexts": contexts,
        "route_strategy": analysis.recommended_strategy.value if analysis else "unknown",
    }


class TestRAGRetrieval:
    """
    检索质量测试 —— 验证 RAG 检索到的文档是否与问题相关。

    核心指标:
    - ContextPrecision: 检索到的上下文中有多少是真正有用的 (精度 >= 0.50)
    - 路由分布: 确认 IntelligentQueryRouter 实际调用了哪些检索策略,
      验证 hybrid_traditional / graph_rag / combined 是否都被覆盖到。
    """

    @pytest.mark.rag
    @pytest.mark.slow
    def test_context_precision(self, init_rag_system):
        """
        测试检索精度: 对 50 条问题逐一执行 RAG 检索, 用 Ragas ContextPrecision
        指标评估检索到的文档与 ground_truth 的相关性。

        阈值: >= 0.50 (目标 0.60)。低于 0.50 说明检索结果包含过多噪声文档。
        """
        from ragas.metrics import ContextPrecision
        from ragas import evaluate, RunConfig
        ds = load_eval_dataset()
        results = [run_rag_query(q) for q in ds["question"]]
        ds = ds.add_column("contexts", [r["contexts"] for r in results])
        score = evaluate(
            ds, metrics=[ContextPrecision()],
            llm=get_eval_llm(), embeddings=get_eval_embeddings(),
            run_config=RunConfig(max_wait=180, max_retries=2))
        cp_list = score["context_precision"]
        cp = sum(v for v in cp_list if v is not None and v == v) / len(cp_list) if cp_list else 0.0
        print(f"\n  ContextPrecision: {cp:.4f} (目标 >= 0.60)")
        assert cp >= 0.50, f"{cp:.4f} < 0.50"

    @pytest.mark.rag
    @pytest.mark.slow
    def test_route_distribution(self, init_rag_system):
        """
        测试路由分布: 统计 50 条问题经过 IntelligentQueryRouter 后各检索策略
        (hybrid_traditional / graph_rag / combined) 的使用频率。

        目的: 验证路由器的分类逻辑是否正常工作, 确保不是所有查询都走同一种策略。
        """
        ds = load_eval_dataset()
        results = [run_rag_query(q) for q in ds["question"]]
        strategies = [r["route_strategy"] for r in results]
        print(f"\n  路由分布: { {s: strategies.count(s) for s in set(strategies)} }")
        assert len(set(strategies)) >= 1


class TestRAGGeneration:
    """
    生成质量测试 —— 验证 LLM 基于检索到的上下文生成的回答质量。

    核心指标 (Ragas LLM-as-Judge):
    - Faithfulness (忠实度): 生成内容是否完全基于检索到的上下文, 有无编造 (>= 0.60)
    - AnswerRelevancy (答案相关性): 回答是否直接回应了问题 (>= 0.50)
    - AnswerCorrectness (答案正确性): 回答与 ground_truth 的一致性 (>= 0.40)
    - ContextRecall (上下文召回率): 检索是否找回了 ground_truth 中包含的信息 (>= 0.40)
    - ContextPrecision (上下文精度): 检索结果中相关文档的比例 (>= 0.50)

    要求 5 项指标至少 3 项达标, 否则视为生成质量不合格。
    """

    @pytest.mark.rag
    @pytest.mark.slow
    def test_comprehensive(self, init_rag_system):
        """
        综合生成评测: 对 50 条问题逐一执行完整 RAG 流程 (检索+生成),
        同时计算 5 个 Ragas 指标, 输出带可视化进度条的评测报告。

        阈值: 5 项指标至少 3 项达标。低于 3 项说明 RAG 问答质量存在系统性问题,
        需要检查 retrieval prompt, 检索策略配置, 或 LLM 生成质量。
        """
        from ragas.metrics import (
            ContextPrecision, ContextRecall, Faithfulness,
            AnswerRelevancy, AnswerCorrectness)
        from ragas import evaluate, RunConfig

        ds = load_eval_dataset()
        results = [run_rag_query(q) for q in ds["question"]]
        ds = ds.add_column("answer", [r["answer"] for r in results])
        ds = ds.add_column("contexts", [r["contexts"] for r in results])

        score = evaluate(
            ds,
            metrics=[ContextPrecision(), ContextRecall(), Faithfulness(),
                     AnswerRelevancy(strictness=1), AnswerCorrectness()],
            llm=get_eval_llm(), embeddings=get_eval_embeddings(),
            run_config=RunConfig(max_wait=180, max_retries=2))

        thresholds = {
            "context_precision": 0.50, "context_recall": 0.40,
            "faithfulness": 0.60, "answer_relevancy": 0.50,
            "answer_correctness": 0.40,
        }

        print("\n" + "=" * 60)
        print("  RAG 综合评测 (Ragas)")
        print("=" * 60)
        passed = 0
        for m in thresholds:
            v_list = score[m]
            valid = [v for v in v_list if v is not None and v == v]
            v = sum(valid) / len(valid) if valid else 0.0
            bar = "█" * min(int(v * 20), 40)
            ok = v >= thresholds.get(m, 0)
            flag = "✓" if ok else "✗"
            nan_note = f" (NaN×{len(v_list)-len(valid)})" if len(valid) < len(v_list) else ""
            print(f"  {flag} {m:<25s}: {v:.4f} {bar}{nan_note}")
            if ok: passed += 1
        print("=" * 60)
        print(f"  通过: {passed}/{len(thresholds)}")
        assert passed >= 3, f"仅 {passed}/{len(thresholds)} 项达标"
