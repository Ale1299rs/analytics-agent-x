from ..config import (
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from .base import LLMClient


class OpenAIClient(LLMClient):
    def __init__(self):
        super().__init__(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
            model=OPENAI_MODEL,
            provider_name="OpenAI",
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
        )
