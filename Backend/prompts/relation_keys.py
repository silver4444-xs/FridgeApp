"""_llm_enhance_relation_keys() 的 Prompt 模板"""

from langchain_core.prompts import ChatPromptTemplate

ENHANCE_RELATION_KEYS = ChatPromptTemplate.from_messages([
    ("system", "分析以下实体关系，生成相关的主题关键词，输出JSON格式结果：\n\n源实体: {source_name} ({source_type})\n目标实体: {target_name} ({target_type})\n关系类型: {relation_type}\n\n请生成3-5个相关的主题关键词，用于索引和检索。"),
])
