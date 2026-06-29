"""understand_graph_query() 的 Prompt 模板"""

from langchain_core.prompts import ChatPromptTemplate

SYSTEM_GRAPH_STRUCTURE = """已知图中大致有以下节点和关系：
- 节点类型：
  - Recipe：菜谱节点，包含 name、description、cuisineType（如"川菜"）、category、tags、prepTime、cookTime 等属性
  - Ingredient：食材节点，包含 name、category（如"蔬菜"、"蛋白质" 等）
  - Category：菜品分类（如"川菜"、"家常菜"、"素菜"）
  - CookingStep：烹饪步骤
- 主要关系：
  - (Recipe)-[:REQUIRES]->(Ingredient)
  - (Recipe)-[:BELONGS_TO_CATEGORY]->(Category)
  - (Recipe)-[:CONTAINS_STEP]->(CookingStep)"""

SYSTEM_QUERY_ANALYSIS = """请识别：
1. 查询类型：
   - entity_relation: 询问实体间的直接关系（如：鸡肉和胡萝卜能一起做菜吗？）
   - multi_hop: 需要多跳推理（如：鸡肉配什么蔬菜？需要：鸡肉→菜品→食材→蔬菜）
   - subgraph: 需要完整子图（如：川菜有什么特色？需要川菜相关的完整知识网络）
   - path_finding: 路径查找（如：从食材到成品菜的制作路径）
   - clustering: 聚类相似性（如：和宫保鸡丁类似的菜有哪些？）

2. source_entities：
   - 只包含在图中**很有可能有对应节点**的具体实体名称
   - 优先选择：菜系（如"川菜"）、具体菜名（如"宫保鸡丁"）、食材名（如"鸡肉"、"豆腐"）
   - 不要把抽象概念或约束（如"糖尿病饮食限制"、"具体川菜菜品"、"健康饮食"、"30分钟内"）放进 source_entities

3. target_entities：
   - 只在确实需要限制「路径终点」时填写
   - 同样只能使用可能出现在 Recipe / Ingredient / Category 节点上的名称（如"蔬菜"、"素菜"、具体菜名）
   - 如果不确定目标实体怎么映射到图中，请返回空列表 []

4. relation_types：本次推理中希望优先考虑的关系类型列表
   - 例如：["REQUIRES", "BELONGS_TO_CATEGORY"]

5. max_depth：建议的图遍历深度（1-3 之间的整数）

6. constraints：可选的**属性级约束**，用于表达图结构之外的过滤条件，例如：
   - 健康/饮食限制（如"糖尿病"、"低糖"）
   - 时间限制（如"30分钟内"）
   - 口味偏好（如"清淡"、"少油"）
   用一个字典描述，例如：
   {{
     "health": ["糖尿病", "低糖"],
     "time": {{"max_minutes": 30}},
     "style": ["川菜"]
   }}

示例1：
查询："鸡肉配什么蔬菜好？"
期望分析：这是 multi_hop 查询，需要通过"鸡肉→使用鸡肉的菜品→这些菜品使用的蔬菜"的路径推理。

返回JSON示例：
{{
  "query_type": "multi_hop",
  "source_entities": ["鸡肉"],
  "target_entities": ["蔬菜"],
  "relation_types": ["REQUIRES", "BELONGS_TO_CATEGORY"],
  "max_depth": 3,
  "constraints": {{}}
}}

示例2：
查询："适合糖尿病人吃的低糖川菜有哪些，并且制作时间不超过30分钟？"
期望分析：
  - 图中可以直接对应的实体：主要是菜系 "川菜"
  - 糖尿病/低糖/30分钟 属于属性级约束，不能当作节点
  - 可以使用 subgraph 或 multi_hop，以 "川菜" 为核心实体，结合属性约束做后续过滤

返回JSON示例：
{{
  "query_type": "subgraph",
  "source_entities": ["川菜"],
  "target_entities": [],
  "relation_types": ["BELONGS_TO_CATEGORY", "REQUIRES"],
  "max_depth": 2,
  "constraints": {{
    "health": ["糖尿病", "低糖"],
    "time": {{"max_minutes": 30}}
  }}
}}"""

UNDERSTAND_GRAPH_QUERY = ChatPromptTemplate.from_messages([
    ("system", f"""作为图数据库专家，分析以下查询的图结构意图，并将自然语言问题映射到**已有图结构**上。

{SYSTEM_GRAPH_STRUCTURE}

请根据上述图结构分析下面的查询。

{SYSTEM_QUERY_ANALYSIS}"""),
    ("user", "查询：{query}"),
])
