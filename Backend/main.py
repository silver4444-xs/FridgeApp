"""
基于图RAG的智能烹饪助手 - 主程序
整合传统检索和图RAG检索，实现真正的图数据优势
"""

import os
import sys
import time
import logging
from typing import List, Optional

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 添加当前目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from config import get_default_config, GraphRAGConfig
from rag_modules import (
    GraphDataPreparationModule,
    MilvusIndexConstructionModule,
    GenerationIntegrationModule
)
from rag_modules.hybrid_retrieval import HybridRetrievalModule
from rag_modules.graph_rag_retrieval import GraphRAGRetrieval
from rag_modules.intelligent_query_router import IntelligentQueryRouter, QueryAnalysis

# 加载环境变量
load_dotenv()


class AdvancedGraphRAGSystem:
    """
    图RAG系统

    核心特性：
    1. 智能路由：自动选择最适合的检索策略
    2. 双引擎检索：传统混合检索 + 图RAG检索
    3. 图结构推理：多跳遍历、子图提取、关系推理
    4. 查询复杂度分析：深度理解用户意图
    5. 自适应学习：基于反馈优化系统性能
    """

    def __init__(self, config: Optional[GraphRAGConfig] = None):
        self.config = config or get_default_config()

        # 核心模块
        self.data_module = None
        self.index_module = None
        self.generation_module = None

        # 检索引擎
        self.traditional_retrieval = None
        self.graph_rag_retrieval = None
        self.query_router = None

        # 系统状态
        self.system_ready = False

    def initialize_system(self):
        """初始化高级图RAG系统"""
        logger.info("启动高级图RAG系统...")

        try:
            # 1. 数据准备模块
            print("初始化数据准备模块...")
            self.data_module = GraphDataPreparationModule(
                uri=self.config.neo4j_uri,
                user=self.config.neo4j_user,
                password=self.config.neo4j_password,
                database=self.config.neo4j_database
            )
            self.data_module.ensure_fulltext_indexes()

            # 2. 向量索引模块
            print("初始化Milvus向量索引...")
            self.index_module = MilvusIndexConstructionModule(
                host=self.config.milvus_host,
                port=self.config.milvus_port,
                collection_name=self.config.milvus_collection_name,
                dimension=self.config.milvus_dimension,
                model_name=self.config.embedding_model
            )

            # 3. 生成模块
            print("初始化生成模块...")
            self.generation_module = GenerationIntegrationModule(
                model_name=self.config.llm_model,
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens
            )

            # 4. 传统混合检索模块
            print("初始化传统混合检索...")
            self.traditional_retrieval = HybridRetrievalModule(
                config=self.config,
                milvus_module=self.index_module,
                data_module=self.data_module,
                llm_client=self.generation_module.lc_client
            )

            # 5. 图RAG检索模块
            print("初始化图RAG检索引擎...")
            self.graph_rag_retrieval = GraphRAGRetrieval(
                config=self.config,
                llm_client=self.generation_module.lc_client
            )

            # 6. 智能查询路由器
            print("初始化智能查询路由器...")
            self.query_router = IntelligentQueryRouter(
                traditional_retrieval=self.traditional_retrieval,
                graph_rag_retrieval=self.graph_rag_retrieval,
                llm_client=self.generation_module.lc_client,
                config=self.config
            )

            print("✅ 高级图RAG系统初始化完成！")

        except Exception as e:
            logger.error(f"系统初始化失败: {e}")
            raise

    def build_knowledge_base(self):
        """构建知识库（如果需要）"""
        print("\n检查知识库状态...")

        try:
            # 检查Milvus集合是否存在
            if self.index_module.has_collection():
                print("✅ 发现已存在的知识库，尝试加载...")
                if self.index_module.load_collection():
                    print("知识库加载成功！")

                    # 重要：即使从已存在的知识库加载，也需要加载图数据以支持图索引
                    print("加载图数据以支持图检索...")
                    self.data_module.load_graph_data()
                    print("构建菜谱文档...")
                    self.data_module.build_recipe_documents()
                    print("进行文档分块...")
                    chunks = self.data_module.chunk_documents(
                        chunk_size=self.config.chunk_size,
                        chunk_overlap=self.config.chunk_overlap
                    )
                    ck_docs = self.data_module.build_cooking_knowledge_documents()
                    chunks.extend(ck_docs)

                    self._initialize_retrievers(chunks)
                    return
                else:
                    print("❌ 知识库加载失败，开始重建...")

            print("未找到已存在的集合，开始构建新的知识库...")

            # 从Neo4j加载图数据
            print("从Neo4j加载图数据...")
            self.data_module.load_graph_data()

            # 构建菜谱文档
            print("构建菜谱文档...")
            self.data_module.build_recipe_documents()

            # 进行文档分块
            print("进行文档分块...")
            chunks = self.data_module.chunk_documents(
                chunk_size=self.config.chunk_size,
                chunk_overlap=self.config.chunk_overlap
            )

            # 加载烹饪知识文档
            print("加载烹饪知识文档...")
            ck_docs = self.data_module.build_cooking_knowledge_documents()
            chunks.extend(ck_docs)

            # 构建Milvus向量索引
            print("构建Milvus向量索引...")
            if not self.index_module.build_vector_index(chunks):
                raise Exception("构建向量索引失败")

            # 初始化检索器
            self._initialize_retrievers(chunks)

            # 显示统计信息
            self._show_knowledge_base_stats()

            print("✅ 知识库构建完成！")

        except Exception as e:
            logger.error(f"知识库构建失败: {e}")
            raise

    def _initialize_retrievers(self, chunks: List = None):
        """初始化检索器"""
        print("初始化检索引擎...")

        # 如果没有chunks，从数据模块获取
        if chunks is None:
            chunks = self.data_module.chunks or []

        # 初始化传统检索器
        self.traditional_retrieval.initialize(chunks)

        # 初始化图RAG检索器
        self.graph_rag_retrieval.initialize()

        self.system_ready = True
        print("✅ 检索引擎初始化完成！")

    def _show_knowledge_base_stats(self):
        """显示知识库统计信息"""
        print(f"\n知识库统计:")

        # 数据统计
        stats = self.data_module.get_statistics()
        print(f"   菜谱数量: {stats.get('total_recipes', 0)}")
        print(f"   食材数量: {stats.get('total_ingredients', 0)}")
        print(f"   烹饪步骤: {stats.get('total_cooking_steps', 0)}")
        print(f"   文档数量: {stats.get('total_documents', 0)}")
        print(f"   文本块数: {stats.get('total_chunks', 0)}")

        # Milvus统计
        milvus_stats = self.index_module.get_collection_stats()
        print(f"   向量索引: {milvus_stats.get('row_count', 0)} 条记录")

        # 图RAG统计
        route_stats = self.query_router.get_route_statistics()
        print(f"   路由统计: 总查询 {route_stats.get('total_queries', 0)} 次")

        if stats.get('categories'):
            categories = list(stats['categories'].keys())[:10]
            print(f"   🏷️ 主要分类: {', '.join(categories)}")

    def ask_question_with_routing(self, question: str, stream: bool = False, explain_routing: bool = False):
        """
        智能问答：自动选择最佳检索策略
        """
        if not self.system_ready:
            raise ValueError("系统未就绪，请先构建知识库")

        print(f"\n❓ 用户问题: {question}")

        # 显示路由决策解释（可选）
        if explain_routing:
            explanation = self.query_router.explain_routing_decision(question)
            print(explanation)

        start_time = time.time()

        try:
            # 1. 智能路由检索
            print("执行智能查询路由...")
            relevant_docs, analysis = self.query_router.route_query(question, self.config.top_k)

            # 2. 显示路由信息
            strategy_icons = {
                "hybrid_traditional": "🔍",
                "graph_rag": "🕸️",
                "combined": "🔄"
            }
            strategy_icon = strategy_icons.get(analysis.recommended_strategy.value, "❓")
            print(f"{strategy_icon} 使用策略: {analysis.recommended_strategy.value}")
            print(f"📊 复杂度: {analysis.query_complexity:.2f}, 关系密集度: {analysis.relationship_intensity:.2f}")

            # 3. 显示检索结果信息
            if relevant_docs:
                doc_info = []
                for doc in relevant_docs:
                    recipe_name = doc.metadata.get('recipe_name', '未知内容')
                    search_type = doc.metadata.get('search_type', doc.metadata.get('route_strategy', 'unknown'))
                    score = doc.metadata.get('final_score', doc.metadata.get('relevance_score', 0))
                    doc_info.append(f"{recipe_name}({search_type}, {score:.3f})")

                print(f"📋 找到 {len(relevant_docs)} 个相关文档: {', '.join(doc_info[:3])}")
                if len(doc_info) > 3:
                    print(f"    等 {len(relevant_docs)} 个结果...")
            else:
                return "抱歉，没有找到相关的烹饪信息。请尝试其他问题。", analysis, []

            # 4. 生成回答
            print("🎯 智能生成回答...")

            if stream:
                try:
                    for chunk_text in self.generation_module.generate_adaptive_answer_stream(question, relevant_docs):
                        print(chunk_text, end="", flush=True)
                    print("\n")
                    result = "流式输出完成"
                except Exception as stream_error:
                    logger.error(f"流式输出过程中出现错误: {stream_error}")
                    print(f"\n⚠️ 流式输出中断，切换到标准模式...")
                    # 使用非流式作为后备
                    result = self.generation_module.generate_adaptive_answer(question, relevant_docs)
            else:
                result = self.generation_module.generate_adaptive_answer(question, relevant_docs)

            # 5. 性能统计
            end_time = time.time()
            print(f"\n⏱️ 问答完成，耗时: {end_time - start_time:.2f}秒")

            return result, analysis, relevant_docs

        except Exception as e:
            logger.error(f"问答处理失败: {e}")
            return f"抱歉，处理问题时出现错误：{str(e)}", None, []

    def run_interactive(self):
        """运行交互式问答"""
        if not self.system_ready:
            print("❌ 系统未就绪，请先构建知识库")
            return

        print("\n欢迎使用尝尝咸淡RAG烹饪助手！")
        print("可用功能：")
        print("   - 'stats' : 查看系统统计")
        print("   - 'rebuild' : 重建知识库")
        print("   - 'quit' : 退出系统")
        print("\n" + "=" * 50)

        while True:
            try:
                user_input = input("\n您的问题: ").strip()

                if not user_input:
                    continue

                if user_input.lower() == 'quit':
                    break
                elif user_input.lower() == 'stats':
                    self._show_system_stats()
                    continue
                elif user_input.lower() == 'rebuild':
                    self._rebuild_knowledge_base()
                    continue

                # 普通问答 - 使用默认设置
                use_stream = True  # 默认使用流式输出
                explain_routing = False  # 默认不显示路由决策

                print("\n回答:")

                result, analysis, _ = self.ask_question_with_routing(
                    user_input,
                    stream=use_stream,
                    explain_routing=explain_routing
                )

                if not use_stream and result:
                    print(f"{result}\n")

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"处理问题时出错: {e}")
                import traceback
                traceback.print_exc()

        print("\n👋 感谢使用尝尝咸淡RAG烹饪助手！")
        self._cleanup()

    def _show_system_stats(self):
        """显示系统统计信息"""
        print("\n系统运行统计")
        print("=" * 40)

        # 路由统计
        route_stats = self.query_router.get_route_statistics()
        total_queries = route_stats.get('total_queries', 0)

        if total_queries > 0:
            print(f"总查询次数: {total_queries}")
            print(
                f"传统检索: {route_stats.get('traditional_count', 0)} ({route_stats.get('traditional_ratio', 0):.1%})")
            print(f"图RAG检索: {route_stats.get('graph_rag_count', 0)} ({route_stats.get('graph_rag_ratio', 0):.1%})")
            print(f"组合策略: {route_stats.get('combined_count', 0)} ({route_stats.get('combined_ratio', 0):.1%})")
        else:
            print("暂无查询记录")

        # 知识库统计
        self._show_knowledge_base_stats()

    def _rebuild_knowledge_base(self):
        """重建知识库"""
        print("\n准备重建知识库...")

        # 确认操作
        confirm = input("⚠️  这将删除现有的向量数据并重新构建，是否继续？(y/N): ").strip().lower()
        if confirm != 'y':
            print("❌ 重建操作已取消")
            return

        try:
            print("删除现有的Milvus集合...")
            if self.index_module.delete_collection():
                print("✅ 现有集合已删除")
            else:
                print("删除集合时出现问题，继续重建...")

            # 重新构建知识库
            print("开始重建知识库...")
            self.build_knowledge_base()

            print("✅ 知识库重建完成！")

        except Exception as e:
            logger.error(f"重建知识库失败: {e}")
            print(f"❌ 重建失败: {e}")
            print("建议：请检查Milvus服务状态后重试")

    def _cleanup(self):
        """清理资源"""
        if self.data_module:
            self.data_module.close()
        if self.traditional_retrieval:
            self.traditional_retrieval.close()
        if self.graph_rag_retrieval:
            self.graph_rag_retrieval.close()
        if self.index_module:
            self.index_module.close()


def main():
    """主函数"""
    try:
        print("启动高级图RAG系统...")

        # 创建高级图RAG系统
        rag_system = AdvancedGraphRAGSystem()

        # 初始化系统
        rag_system.initialize_system()

        # 构建知识库
        rag_system.build_knowledge_base()

        # 运行交互式问答
        rag_system.run_interactive()

    except Exception as e:
        logger.error(f"系统运行失败: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n❌ 系统错误: {e}")


# Phase 1: create_agent 标准化 Agent 循环
# 原代码 (上方 AdvancedGraphRAGSystem.ask_question_with_routing):
#   def ask_question_with_routing(self, question, stream=False, ...):
#       # 1. 智能路由检索
#       relevant_docs, analysis = self.query_router.route_query(question, ...)
#       # 2. 生成回答
#       if stream:
#           for chunk in self.generation_module.generate_adaptive_answer_stream(...):
#               print(chunk, end="", flush=True)
#       else:
#           result = self.generation_module.generate_adaptive_answer(...)
#       return result, analysis
#
# 改进后 (下方 create_fridge_agent):
#   使用 LangChain v1 create_agent + @tool 标准化 Agent 循环
#   - LLM 自主决定何时调用 search_recipes_by_ingredients / get_recipe_detail /
#     find_substitutions / search_cooking_knowledge
#   - 无需手工编排路由→检索→生成流程
#   - 自动获得 tool-calling 错误处理、流式输出、对话持久化能力

def create_fridge_agent(model_name: str = None,
                        temperature: float = 0.1,
                        max_tokens: int = 2048,
                        use_context: bool = True,
                        store=None,
                        checkpointer=None,
                        agent_mode: str = "context"):
    """
    使用 LangChain v1 create_agent 创建智能冰箱 Agent。

    agent_mode 控制工具集:
      "basic"    — V1: 4 个基础 tool (兼容旧版)
      "context"  — V2: 8 个 tool + ToolRuntime 上下文感知 (默认)
      "subagents"— V3: 6 个 tool (3 直属 + 3 子 Agent) Phase 6

    if model_name is None:
        model_name = os.getenv("LLM_MODEL", "deepseek-v4-flash")

    Args:
        model_name: 模型名称 (默认从 LLM_MODEL 环境变量读取，回退 deepseek-v4-flash)
        temperature: 生成温度
        max_tokens: 最大 token 数
        use_context: (兼容旧参数) True→agent_mode="context"
        store: 可选的 InMemoryStore/PostgresStore
        checkpointer: 可选的 InMemorySaver/PostgresSaver
        agent_mode: "basic" | "context" | "subagents"

    Returns:
        配置好的 LangChain Agent (Runnable)

    使用示例:
        from api.tools import FridgeContext
        agent = create_fridge_agent()

        result = agent.invoke(
            {"messages": [{"role": "user", "content": "能做什么菜?"}]},
            context=FridgeContext(
                current_inventory=[
                    {"name": "鸡蛋", "qty": 6, "cal": 74, "cat": "肉蛋生鲜类"},
                    {"name": "西红柿", "qty": 3, "cal": 18, "cat": "蔬菜"},
                ],
                user_preferences={"忌口": ["花生"]},
            ),
        )
    """
    import os
    from langchain.agents import create_agent
    from langchain.agents.middleware import (
        HumanInTheLoopMiddleware,
        ModelCallLimitMiddleware,
        ModelRetryMiddleware,
        SummarizationMiddleware,
        ToolRetryMiddleware,
    )
    from langchain.chat_models import init_chat_model
    from langgraph.checkpoint.memory import InMemorySaver
    from langgraph.store.memory import InMemoryStore

    # ── Store 初始化 (Long-term Memory) ──
    # Phase 3.5: 优先使用外部传入的 store (共享实例)，否则创建新的 InMemoryStore
    # 生产环境替换为 PostgresStore: from langgraph.store.postgres import PostgresStore
    if store is None:
        store = InMemoryStore()

    # ── Checkpointer 初始化 (HITL 必需) ──
    # Phase 4: HumanInTheLoopMiddleware 依赖 checkpointer 保存中断状态
    # 优先使用外部传入的 checkpointer，否则创建新的 InMemorySaver
    if checkpointer is None:
        checkpointer = InMemorySaver()

    # ── 工具选择 ──
    # if use_context:
    #     from api.tools import FRIDGE_TOOLS_V2, FridgeContext
    #     tools = FRIDGE_TOOLS_V2; context_schema = FridgeContext
    # else:
    #     from api.tools import FRIDGE_TOOLS
    #     tools = FRIDGE_TOOLS; context_schema = None
    #
    # ── 改进后 (Phase 6): agent_mode 三选一 ──
    # backward compat: use_context=False → "basic"
    if not use_context:
        agent_mode = "basic"

    if agent_mode == "subagents":
        # Phase 6: 3 主 Agent 直属 tool + 3 子 Agent
        from api.tools import FRIDGE_TOOLS_V3, FridgeContext
        from api.subagents import SUBAGENT_TOOLS
        tools = FRIDGE_TOOLS_V3 + SUBAGENT_TOOLS
        context_schema = FridgeContext
        logger.info("FridgeAgent: Subagents 模式 (V3) — 6 tools (3 direct + 3 subagents)")
    elif agent_mode == "context":
        # Phase 1.3/3.5: 8 个 tool + ToolRuntime
        from api.tools import FRIDGE_TOOLS_V2, FridgeContext
        tools = FRIDGE_TOOLS_V2
        context_schema = FridgeContext
        logger.info("FridgeAgent: Context 模式 (V2) — 8 tools")
    else:
        # Phase 1 (basic): 4 个基础 tool
        from api.tools import FRIDGE_TOOLS
        tools = FRIDGE_TOOLS
        context_schema = None
        logger.info("FridgeAgent: Basic 模式 (V1) — 4 tools")

    # ── 模型初始化 ──
    import httpx
    model = init_chat_model(
        f"openai:{model_name}",
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=os.getenv("DEEPSEEK_API_KEY"),
        openai_api_base=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        http_client=httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=60.0, write=10.0, pool=10.0),
        ),
    )

    # ── 系统提示词 ──
    #   每次手工拼接食材+问题上下文
    # 改进后 (Phase 1): 标准化 system_prompt，
    #   LLM 自主理解何时调用哪个 tool
    # 改进后 (Phase 1.3): 新增 get_fridge_inventory / recommend_by_fridge
    #   用户无需罗列食材，Agent 自动从 FridgeContext 读取
    system_prompt = (
        "你是「尝尝咸淡」智能冰箱的菜谱推荐助手。\n"
        "\n"
        "你的能力:\n"
        "1. 查看冰箱当前食材清单 (get_fridge_inventory)\n"
        "2. 基于冰箱食材自动推荐可制作的菜谱 (recommend_by_fridge)\n"
        "3. 根据指定食材搜索菜谱 (search_recipes_by_ingredients)\n"
        "4. 提供菜谱的详细制作步骤和小贴士 (get_recipe_detail)\n"
        "5. 为缺少的食材寻找替代方案 (find_substitutions)\n"
        "6. 回答烹饪技巧、食材处理等知识性问题 (search_cooking_knowledge)\n"
        "\n"
        "工作流程:\n"
        "- 当用户问「能做什么菜」「推荐几个菜」时，直接调用 recommend_by_fridge\n"
        "  (无需先调 get_fridge_inventory，recommend_by_fridge 自动读取冰箱食材)\n"
        "- 当用户想了解某道菜的具体做法时，调用 get_recipe_detail\n"
        "- 当用户缺少某食材时，调用 find_substitutions 查找替代品\n"
        "- 当用户问烹饪技巧时，调用 search_cooking_knowledge\n"
        "- 当用户问「冰箱里有什么」时，调用 get_fridge_inventory\n"
        "\n"
        "规则:\n"
        "- 始终基于工具返回的真实数据回答，不要编造菜谱\n"
        "- 如果工具返回空结果，如实告知用户并给出建议\n"
        "- 回答时标注信息来源（菜谱名称、匹配食材数等）\n"
        "- 推荐菜谱时优先推荐匹配度高的\n"
        "- 用户说「能做什么菜」时直接调 recommend_by_fridge，不要反问用户有哪些食材\n"
        "- 当用户提到饮食偏好、忌口、过敏信息或用餐人数时，调用 save_user_preferences 保存\n"
        "- 每次对话开始时，先调用 get_user_preferences 获取已保存的偏好\n"
        "\n"
        "输出格式规则:\n"
        "- 回答简洁，每次推荐不超过 5 道菜\n"
        "- 使用表格组织对比信息（菜名 | 食材 | 难度 | 时间）\n"
        "- 用 --- 分隔不同主题的内容块\n"
        "- 推荐菜谱时使用编号列表，每道菜一行简短描述\n"
        "- 避免大段描述性文字，优先用结构化格式"
    )

    # ── Phase 6 Subagents 专用 system prompt ──
    if agent_mode == "subagents":
        system_prompt = (
            "你是「尝尝咸淡」智能冰箱管家，协调专业子 Agent 为用户服务。\n"
            "\n"
            "你直属的能力:\n"
            "1. 查看冰箱当前食材清单 (get_fridge_inventory)\n"
            "2. 保存用户饮食偏好到长期记忆 (save_user_preferences)\n"
            "3. 读取已保存的用户偏好 (get_user_preferences)\n"
            "\n"
            "你可以调度的专家:\n"
            "- recipe_expert (菜谱推荐专家): 推荐菜谱、搜索菜谱、查看做法\n"
            "- substitution_expert (食材替换专家): 为缺少的食材找替代方案\n"
            "- cooking_expert (烹饪知识专家): 回答烹饪技巧、食材知识\n"
            "\n"
            "路由规则:\n"
            "- 凡是涉及「推荐菜/做什么菜/搜索菜谱/菜的做法」→ 调用 recipe_expert\n"
            "- 凡是涉及「代替/替换/缺XX怎么办」→ 调用 substitution_expert\n"
            "- 凡是涉及「烹饪技巧/食材知识/怎么做更好吃」→ 调用 cooking_expert\n"
            "- 问「冰箱里有什么」→ 调用 get_fridge_inventory\n"
            "- 用户声明饮食偏好 → 调用 save_user_preferences\n"
            "\n"
            "你的职责是理解用户需求 → 路由到对应专家 → 综合专家的回答返回给用户。\n"
            "不要自己回答菜谱推荐、替换建议、烹饪知识类问题，交给专家处理。"
        )

    # ── 创建 Agent ──
    #   query_router.route_query() → generate_adaptive_answer()
    # 改进后 (Phase 1): create_agent(tools=FRIDGE_TOOLS)
    #   一行创建，LLM 自主 tool-calling
    # 改进后 (Phase 1.3): create_agent(tools=FRIDGE_TOOLS_V2, context_schema=...)
    #   注入 FridgeContext，工具通过 ToolRuntime 自动读取冰箱食材
    #   用户只需说「能做什么菜」无需罗列食材
    # ── 改造前代码 (Phase 1.3): ──
    # agent_kwargs = dict(
    #     model=model,
    #     tools=tools,
    #     system_prompt=system_prompt,
    # )
    # if context_schema is not None:
    #     agent_kwargs["context_schema"] = context_schema
    # agent = create_agent(**agent_kwargs)
    #
    # ── 改进后 (Phase 3 Middleware + Phase 3.5 Store + Phase 4 HITL): ──
    # ModelCallLimitMiddleware: 单次 invoke 最多 15 次模型调用
    # SummarizationMiddleware: 对话超过 4000 token 自动摘要压缩
    # HumanInTheLoopMiddleware: 写操作(save_user_preferences)需人工审批
    #   - checkpointer=InMemorySaver(): HITL 必需，保存中断状态
    #   - 恢复执行: agent.invoke(Command(resume={"decisions":[{"type":"approve"}]}), config)
    # ToolRetryMiddleware: 工具层容错重试
    # ModelRetryMiddleware: LLM API 调用容错重试
    # store=InMemoryStore(): 跨会话持久化用户偏好
    # 原 create_agent(**agent_kwargs) 展开为显式参数 + middleware + store + checkpointer
    agent_kwargs = dict(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )
    if context_schema is not None:
        agent_kwargs["context_schema"] = context_schema

    import api.dependencies as deps
    deps.fridge_model = model

    agent = create_agent(
        **agent_kwargs,
        store=store,
        checkpointer=checkpointer,
        middleware=[
            ModelCallLimitMiddleware(
                run_limit=15,
                exit_behavior="end",
            ),
            SummarizationMiddleware(
                model=model,
                trigger=("tokens", 4000),
                keep=("messages", 10),
                summary_prompt=(
                    "请用中文简洁总结以下对话的关键信息，包括：\n"
                    "1. 用户提到的饮食偏好和忌口\n"
                    "2. 讨论过并得到用户认可的菜谱\n"
                    "3. 用户明确提出的需求或问题\n"
                    "4. 重要的上下文信息\n\n"
                    "对话内容:\n{messages}"
                ),
            ),
            HumanInTheLoopMiddleware(
                interrupt_on={
                    "save_user_preferences": {
                        "allowed_decisions": ["approve", "reject"],
                        "description": "保存用户饮食偏好到长期记忆",
                    },
                    # 未来扩展 (Phase 4.1):
                    # "clear_inventory": {
                    #     "allowed_decisions": ["approve", "reject"],
                    #     "description": "清空冰箱 - 将删除所有食材记录",
                    # },
                    # "delete_favorite_recipes": {
                    #     "allowed_decisions": ["approve", "reject"],
                    #     "description": "删除收藏菜谱",
                    # },
                },
                description_prefix="操作待确认",
            ),
            ModelRetryMiddleware(
                max_retries=3,
                backoff_factor=2.0,
                initial_delay=1.0,
                max_delay=30.0,
                jitter=True,
            ),
            ToolRetryMiddleware(
                max_retries=2,
                tools=[
                    "find_substitutions", "search_cooking_knowledge",
                    "recipe_expert", "substitution_expert", "cooking_expert",
                ],
                initial_delay=0.5,
                max_delay=10.0,
                backoff_factor=2.0,
                jitter=True,
                on_failure="return_message",
            ),
        ],
    )

    logger.info(f"FridgeAgent 创建完成 (model={model_name}, "
                f"tools={[t.name for t in tools]}, "
                f"checkpointer=InMemorySaver, "
                f"store=InMemoryStore(namespaces=preferences), "
                f"middleware=[ModelCallLimitMiddleware(run_limit=15), "
                f"SummarizationMiddleware(trigger=4000tokens), "
                f"HumanInTheLoopMiddleware(interrupt_on=save_user_preferences), "
                f"ModelRetryMiddleware(max_retries=3), "
                f"ToolRetryMiddleware(max_retries=2, tools=2)])")
    return agent


def create_fridge_agent_from_rag(rag_system: "AdvancedGraphRAGSystem" = None,
                                 model_name: str = "deepseek-v4-flash",
                                 temperature: float = 0.1,
                                 max_tokens: int = 2048,
                                 store=None,
                                 checkpointer=None,
                                 agent_mode: str = "context"):
    """
    在 RAG 系统初始化完成后创建 Agent。

    确保 api.dependencies.rag_system 已设置后再调用此函数。

    Fix #11: rag_system 参数保留供未来扩展 (如注入 RAG 检索器到 tool)，
    当前 Agent 通过 api.dependencies 访问 rag_system 单例。
    """
    # Fix #11: 明确标注 rag_system 为预留扩展点，避免误解为死代码
    _ = rag_system  # 预留: 未来可将 RAG 检索器注入 Agent middleware
    return create_fridge_agent(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        store=store,
        checkpointer=checkpointer,
        agent_mode=agent_mode,
    )


# Phase 2: LangGraph StateGraph 包装
#   result = agent.invoke({"messages": [...]})
#   result = agent.invoke({"messages": [...]})  # 上一轮历史丢失
#
#   graph.invoke({...}, config={"configurable": {"thread_id": "user_abc"}})
#   graph.invoke({...}, config={"configurable": {"thread_id": "user_abc"}})
#   # ↑ 第二轮自动继承第一轮对话历史

def create_fridge_graph_wrapper(rag_system: "AdvancedGraphRAGSystem" = None,
                                model_name: str = "deepseek-v4-flash",
                                temperature: float = 0.1,
                                max_tokens: int = 2048,
                                checkpointer=None,
                                store=None):
    """(checkpointer 和 store 均透传至 Agent 和 Graph)"""
    """
    创建 LangGraph StateGraph，包装 create_agent 实例。

    构建 START → recommend(Agent) → END 的状态图，
    注入 InMemorySaver 实现多轮对话持久化。

    Args:
        rag_system: 已初始化的 RAG 系统 (可选)
        model_name: 模型名称
        temperature: 生成温度
        max_tokens: 最大 token 数
        checkpointer: 检查点存储器 (默认 InMemorySaver)
        store: Long-term Memory Store (默认 None)

    Returns:
        编译后的 CompiledStateGraph

    使用示例:
        graph = create_fridge_graph_wrapper()

        # 多轮对话 (相同 thread_id 自动继承上下文)
        config = {"configurable": {"thread_id": "user_abc"}}
        r1 = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "能做什么菜?"}]},
            config=config,
        )
        r2 = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "第一个菜的具体步骤?"}]},
            config=config,  # 相同 thread_id → 自动继承上文
        )
    """
    from api.graph import create_fridge_graph

    # 创建 Agent (传入 store + checkpointer 实现 Long-term Memory + HITL)
    agent = create_fridge_agent(
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        use_context=True,
        store=store,
        checkpointer=checkpointer,
    )

    # 包装为 StateGraph (传入 store 确保 Graph 内 tool 也可访问)
    graph = create_fridge_graph(
        fridge_agent=agent,
        checkpointer=checkpointer,
        store=store,
    )

    store_info = f" + Store({type(store).__name__})" if store else ""
    logger.info(f"FridgeGraph 包装完成 (Agent + StateGraph + Checkpointer{store_info})")
    return graph


if __name__ == "__main__":
    main()