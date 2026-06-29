"""Prompt 模板 — 集中管理所有 LLM 调用模板（Step 3）"""

from .graph_query import UNDERSTAND_GRAPH_QUERY
from .query_analysis import ANALYZE_QUERY
from .keyword_extraction import EXTRACT_QUERY_KEYWORDS
from .answer_generation import GENERATE_ADAPTIVE_ANSWER
from .relation_keys import ENHANCE_RELATION_KEYS

__all__ = [
    "UNDERSTAND_GRAPH_QUERY",
    "ANALYZE_QUERY",
    "EXTRACT_QUERY_KEYWORDS",
    "GENERATE_ADAPTIVE_ANSWER",
    "ENHANCE_RELATION_KEYS",
]
