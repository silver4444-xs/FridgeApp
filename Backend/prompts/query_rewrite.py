"""rewrite_query() 的 Prompt 模板

将用户口语化的烹饪查询改写为更适合检索的形式。
"""

from langchain_core.prompts import ChatPromptTemplate

REWRITE_QUERY = ChatPromptTemplate.from_messages([
    ("system", """将用户的口语化烹饪查询改写为更适合检索的形式。严格按指定 JSON 字段名输出。

改写规则:
1. 移除口语词 (如 "有点"、"啥"、"好吃的"、"咋做"、"弄一下")
2. 补充关键同义词 (如 鸡胸肉→鸡肉/鸡胸, 土豆→马铃薯/洋芋, 番茄→西红柿)
3. 提取核心食材实体和烹饪意图
4. 保持原意不变, 不要添加用户没提过的信息
5. 如查询已经清晰简洁, 可直接复用原文

JSON 字段说明 (必须使用这些字段名):
- rewritten (str): 改写后的查询文本, 适合 BM25 + 向量 + 图三种检索方式
- entities (list[str]): 从查询中提取的核心实体 (食材名/菜名/烹饪工具等)
- intent (str): 烹饪意图, 可选值: "recipe_search"(找菜谱) / "cooking_knowledge"(问技巧) / "substitution"(找替代) / "recommendation"(求推荐) / "general"(其他)
- filters (dict[str, str]): 从查询中提取的过滤条件。可选键: difficulty(easy/medium/hard), cuisine_type(川菜/粤菜等), tag(低脂/快手等)。无明确约束时为空dict"""),
    ("user", "用户查询: {query}"),
])
