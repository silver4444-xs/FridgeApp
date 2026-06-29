"""extract_query_keywords() 的 Prompt 模板"""

from langchain_core.prompts import ChatPromptTemplate

EXTRACT_QUERY_KEYWORDS = ChatPromptTemplate.from_messages([
    ("system", """作为烹饪知识助手，请分析以下查询并提取关键词，分为两个层次：

提取规则：
1. 实体级关键词：具体的食材、菜品名称、工具、品牌等有形实体
   - 例如：鸡胸肉、西兰花、红烧肉、平底锅、老干妈
   - 对于抽象查询，推测相关的具体食材/菜品

2. 主题级关键词：抽象概念、烹饪主题、饮食风格、营养特点等
   - 例如：减肥、低热量、川菜、素食、下饭菜、快手菜
   - 排除动作词：推荐、介绍、制作、怎么做等

示例：
查询："推荐几个减肥菜"
{{
    "entity_keywords": ["鸡胸肉", "西兰花", "水煮蛋", "胡萝卜", "黄瓜"],
    "topic_keywords": ["减肥", "低热量", "高蛋白", "低脂"]
}}

查询："川菜有什么特色"
{{
    "entity_keywords": ["麻婆豆腐", "宫保鸡丁", "水煮鱼", "辣椒", "花椒"],
    "topic_keywords": ["川菜", "麻辣", "香辣", "下饭菜"]
}}"""),
    ("user", "查询：{query}"),
])
