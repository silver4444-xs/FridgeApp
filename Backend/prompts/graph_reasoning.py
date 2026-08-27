"""graph_structure_reasoning() 的 Prompt 模板 —— 基于图结构的多跳推理"""

from langchain_core.prompts import ChatPromptTemplate

GRAPH_SCHEMA_DESCRIPTION = """已知图数据库 Schema:
- 节点类型:
  - Recipe: 菜谱 (属性: name, category, cuisineType, tags, prepTime, cookTime, description)
  - Ingredient: 食材 (属性: name, category)
  - Category: 菜品分类 (属性: name)
  - CookingStep: 烹饪步骤 (属性: name, stepNumber, description, methods, tools)
- 关系类型:
  - (Recipe)-[:REQUIRES]->(Ingredient)  菜谱需要某食材
  - (Recipe)-[:BELONGS_TO_CATEGORY]->(Category)  菜谱属于某分类
  - (Recipe)-[:CONTAINS_STEP]->(CookingStep)  菜谱包含某步骤
  - (Ingredient)-[:SAME_AS]->(Ingredient)  同义食材"""

REASONING_INSTRUCTIONS = """你是一个图结构推理专家。基于上述图 Schema 和下方提供的**真实子图数据**，结合用户的查询问题，完成以下任务:

1. **识别推理模式** (reasoning_patterns):
   从子图的节点类型和关系结构中识别存在哪些推理模式，例如:
   - 组成推理 (composition): Recipe 通过 REQUIRES 连接到多个 Ingredient, 分析食材组合
   - 分类推理 (taxonomy): Recipe 通过 BELONGS_TO_CATEGORY 归入 Category, 分析菜系/分类特征
   - 流程推理 (procedural): Recipe 通过 CONTAINS_STEP 组织 CookingStep, 分析烹饪流程
   - 相似推理 (similarity): 两个 Recipe 共享多个 Ingredient 或属于同一 Category
   - 替代推理 (substitution): 相似食材通过 SAME_AS 关联, 分析替代关系
   - 跨层推理 (cross-layer): 通过多跳路径连接不同层次的实体

2. **构建推理链** (reasoning_chains):
   为每个识别出的推理模式构建一条具体的推理链，要求:
   - **必须引用子图中真实存在的节点名称和关系类型** (从下方子图数据中查找)
   - 推理链用中文自然语言表达，格式: "推理类型: 具体推理路径 —— 涉及实体: [列出具体名称]"
   - 推理链必须与用户查询相关，回答查询中的隐含问题
   - 每条推理链控制在 40-120 字之间
   - 如果子图数据不包含某类推理所需的信息，跳过该模式

3. **提取关键发现** (key_insights):
   从子图中提取 2-5 条对回答用户查询有用的关键事实，每条 15-50 字。

重要约束:
- 所有结论必须严格基于下方子图数据，不得编造图中不存在的节点或关系
- 如果子图数据稀疏或与查询不相关，输出空列表并如实说明
- reasoning_patterns 只列出实际能用子图数据支撑的模式"""

GRAPH_REASONING_PROMPT = ChatPromptTemplate.from_messages([
    ("system", f"{GRAPH_SCHEMA_DESCRIPTION}\n\n{REASONING_INSTRUCTIONS}"),
    ("user", """用户查询: {query}

=== 知识子图数据 ===
{subgraph_text}

请基于以上子图数据进行图结构推理，严格输出 JSON 格式。"""),
])
