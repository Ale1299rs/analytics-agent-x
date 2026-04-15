from ..config import LLM_PROVIDER
from .base import LLMClient
from .deepseek_client import DeepSeekClient
from .openai_client import OpenAIClient


def create_llm_client() -> LLMClient:
    """Create LLM client based on LLM_PROVIDER env var."""
    if LLM_PROVIDER == "openai":
        return OpenAIClient()
    return DeepSeekClient()
