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
- reasoning (str): 推荐理由简述 (15字以内)

策略选择规则（必须严格据此决定 recommended_strategy，不要保守地默认 hybrid_traditional）：
- hybrid_traditional: 单一实体、精确查找、无关系推理。条件: reasoning_required=false 且 query_complexity<0.4 且 relationship_intensity<0.4。例: "红烧肉怎么做"、"口水鸡的做法"。
- graph_rag: 需要多跳关系推理/因果/对比/同义替换/跨实体关联。条件: reasoning_required=true 或 query_complexity>=0.6 或 relationship_intensity>=0.6。例: "为什么川菜用花椒"、"鸡肉可以用什么替代"、"口水鸡和姜炒鸡有什么区别"。
- combined: 既需精确检索又需关系推理的复合查询。条件: query_complexity 与 relationship_intensity 均在 0.4-0.6。
- 判定优先级: 先看 reasoning_required；为 true 时至少 graph_rag(若复杂度与关系密度双高则 combined)；否则取 query_complexity 与 relationship_intensity 的较高者决定。"""),
    ("user", "查询：{query}"),
])
