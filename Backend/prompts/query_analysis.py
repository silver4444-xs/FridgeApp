"""analyze_query() 的 Prompt 模板"""

from langchain_core.prompts import ChatPromptTemplate

ANALYZE_QUERY = ChatPromptTemplate.from_messages([
    ("system", """作为RAG系统的查询分析专家，请深度分析以下查询的特征，严格按指定 JSON 字段名输出：

JSON 字段说明（必须使用这些字段名，不要翻译或重命名）：
- query_complexity (float 0-1): 查询复杂度。0.0-0.3=简单查找(如"红烧肉怎么做")，0.4-0.7=中等(如"川菜有哪些特色菜")，0.8-1.0=高复杂度推理(如"为什么川菜用花椒而不是胡椒")
- relationship_intensity (float 0-1): 关系密集度。0.0-0.3=单一实体，0.4-0.7=实体间关系，0.8-1.0=复杂关系网络
- reasoning_required (bool): 是否需要多跳推理/因果分析/对比分析
- entity_count (int): 查询中明确实体的数量
- recommended_strategy (str): 推荐检索策略，可选 hybrid_traditional / graph_rag / combined
- confidence (float 0-1): 推荐置信度
- reasoning (str): 推荐理由简述 (15字以内)"""),
    ("user", "查询：{query}"),
])
