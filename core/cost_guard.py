from typing import Dict, List


class CostGuard:
    """Tracks LLM usage, query count, and produces cost warnings."""

    def __init__(self, max_llm_calls: int = 10, max_queries: int = 3):
        self.max_llm_calls = max_llm_calls
        self.max_queries = max_queries
        self._prompt_chars = 0
        self._response_chars = 0
        self._llm_calls = 0
        self._query_count = 0
        self._warnings: List[str] = []

    def register_prompt(self, text: str) -> None:
        self._prompt_chars += len(text)
        if len(text) > 5000:
            self._warnings.append(
                f"Prompt lungo ({len(text)} chars) — considera di ridurre il contesto."
            )

    def register_response(self, text: str) -> None:
        self._response_chars += len(text)

    def register_llm_call(self) -> None:
        self._llm_calls += 1
        if self._llm_calls > self.max_llm_calls:
            self._warnings.append(
                f"Superato il limite di {self.max_llm_calls} chiamate LLM."
            )

    def register_query(self) -> None:
        self._query_count += 1
        if self._query_count > self.max_queries:
            self._warnings.append(
                f"Superato il limite di {self.max_queries} query SQL."
            )

    @property
    def budget_exceeded(self) -> bool:
        return self._llm_calls > self.max_llm_calls

    @property
    def warnings(self) -> List[str]:
        return list(self._warnings)

    def summary(self) -> Dict:
        prompt_tokens = max(1, self._prompt_chars // 4) if self._prompt_chars else 0
        response_tokens = max(1, self._response_chars // 4) if self._response_chars else 0
        return {
            "estimated_prompt_chars": self._prompt_chars,
            "estimated_response_chars": self._response_chars,
            "estimated_prompt_tokens": prompt_tokens,
            "estimated_response_tokens": response_tokens,
            "number_of_llm_calls": self._llm_calls,
            "number_of_queries": self._query_count,
            "warnings": list(self._warnings),
        }
