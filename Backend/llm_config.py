"""
LLM 配置模块 — 封装所有大语言模型相关配置，兼容任意 OpenAI-compatible 提供商
"""
import os
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class LLMConfig:
    """LLM 配置类，支持任意 OpenAI-compatible 提供商"""

    provider: str = "deepseek"
    model_name: str = "deepseek-v4-flash"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: str = "https://api.deepseek.com/v1"
    temperature: float = 0.1
    max_tokens: int = 2048

    def get_api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(
                "请设置 {} 环境变量".format(self.api_key_env)
            )
        return key

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "LLMConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "api_key_env": self.api_key_env,
            "base_url": self.base_url,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }


# —— 预设配置 ——

DEEPSEEK = LLMConfig(
    provider="deepseek",
    model_name="deepseek-v4-flash",
    api_key_env="DEEPSEEK_API_KEY",
    base_url="https://api.deepseek.com/v1",
    temperature=0.1,
    max_tokens=2048,
)

KIMI = LLMConfig(
    provider="kimi",
    model_name="kimi-k2-0711-preview",
    api_key_env="MOONSHOT_API_KEY",
    base_url="https://api.moonshot.cn/v1",
    temperature=0.1,
    max_tokens=2048,
)

OPENAI = LLMConfig(
    provider="openai",
    model_name="gpt-4o",
    api_key_env="OPENAI_API_KEY",
    base_url="https://api.openai.com/v1",
    temperature=0.1,
    max_tokens=2048,
)

DEFAULT_LLM_CONFIG = DEEPSEEK


def get_preset(name: str) -> Optional[LLMConfig]:
    """按名称获取预设配置"""
    presets = {
        "deepseek": DEEPSEEK,
        "kimi": KIMI,
        "openai": OPENAI,
    }
    return presets.get(name.lower())
