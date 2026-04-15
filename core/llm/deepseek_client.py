from ..config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_MODEL,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)
from .base import LLMClient


class DeepSeekClient(LLMClient):
    def __init__(self):
        super().__init__(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            model=DEEPSEEK_MODEL,
            provider_name="DeepSeek",
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
        )
