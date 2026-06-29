"""
生成集成模块
"""

import logging
import os
import time
from typing import List

from langchain_openai import ChatOpenAI
from langchain_core.documents import Document

from prompts.answer_generation import GENERATE_ADAPTIVE_ANSWER

logger = logging.getLogger(__name__)

class GenerationIntegrationModule:
    """生成集成模块 - 负责答案生成"""

    def __init__(self, model_name: str = "deepseek-v4-pro", temperature: float = 0.1, max_tokens: int = 2048):
        """
        初始化生成集成模块
        """
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # 初始化OpenAI客户端（使用Moonshot API）
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise ValueError("请设置 DEEPSEEK_API_KEY 环境变量")

        # ChatOpenAI 客户端 (langchain-openai)
        # stream_chunk_timeout: 防止流式调用因 TCP 静默断开而永久挂起 (langchain-openai>=1.2.0)
        self.lc_client = ChatOpenAI(
            model=self.model_name,
            api_key=api_key,
            base_url="https://api.deepseek.com/v1",
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            stream_chunk_timeout=120,
        )

        logger.info(f"生成模块初始化完成，模型: {model_name}")

    def generate_adaptive_answer(self, question: str, documents: List[Document]) -> str:
        """
        智能统一答案生成
        自动适应不同类型的查询，无需预先分类
        """
        # 构建上下文
        context_parts = []
        
        for doc in documents:
            content = doc.page_content.strip()
            if content:
                # 添加检索层级信息（如果有的话）
                level = doc.metadata.get('retrieval_level', '')
                if level:
                    context_parts.append(f"[{level.upper()}] {content}")
                else:
                    context_parts.append(content)
        
        context = "\n\n".join(context_parts)
        
        # ===== 原始内联 f-string Prompt (已提取为 ChatPromptTemplate) =====
        # prompt = f"""
        # 作为一位专业的烹饪助手，请基于以下信息回答用户的问题。
        # 检索到的相关信息：{context}
        # 用户问题：{question}
        # ... (完整 prompt 已迁移至 prompts/answer_generation.py)
        # """

        # ChatPromptTemplate 调用
        try:
            prompt = GENERATE_ADAPTIVE_ANSWER.format(context=context, question=question)
            response = self.lc_client.invoke(prompt)
            return response.content.strip()
        except Exception as e:
            logger.error(f"LightRAG答案生成失败: {e}")
            return f"抱歉，生成回答时出现错误：{str(e)}"
    
    def generate_adaptive_answer_stream(self, question: str, documents: List[Document], max_retries: int = 3):
        """
        LightRAG风格的流式答案生成（带重试机制）
        """
        # 构建上下文
        context_parts = []
        
        for doc in documents:
            content = doc.page_content.strip()
            if content:
                level = doc.metadata.get('retrieval_level', '')
                if level:
                    context_parts.append(f"[{level.upper()}] {content}")
                else:
                    context_parts.append(content)
        
        context = "\n\n".join(context_parts)

        # ChatPromptTemplate 调用
        prompt = GENERATE_ADAPTIVE_ANSWER.format(context=context, question=question)

        # ChatOpenAI 流式调用
        for attempt in range(max_retries):
            try:
                if attempt == 0:
                    print("开始流式生成回答...\n")
                else:
                    print(f"第{attempt + 1}次尝试流式生成...\n")

                for chunk in self.lc_client.stream(prompt):
                    yield chunk.content

                return

            except Exception as e:
                logger.warning(f"流式生成第{attempt + 1}次尝试失败: {e}")

                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"⚠️ 连接中断，{wait_time}秒后重试...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"流式生成完全失败，尝试非流式后备方案")
                    print("⚠️ 流式生成失败，切换到标准模式...")

                    try:
                        fallback_response = self.generate_adaptive_answer(question, documents)
                        yield fallback_response
                        return
                    except Exception as fallback_error:
                        logger.error(f"后备生成也失败: {fallback_error}")
                        error_msg = f"抱歉，生成回答时出现网络错误，请稍后重试。错误信息：{str(e)}"
                        yield error_msg
                        return 