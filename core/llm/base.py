import logging
import time
from typing import Any, Dict

import requests

from ..utils import parse_json_text

logger = logging.getLogger(__name__)

# Retry config
MAX_RETRIES = 2
RETRY_BACKOFF = [1.0, 2.0]
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class LLMClient:
    """Provider-agnostic LLM client with retry and JSON mode support."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
        provider_name: str = "LLM",
        max_tokens: int = 2048,
        temperature: float = 0.2,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.provider_name = provider_name
        self.max_tokens = max_tokens
        self.temperature = temperature
        if not self.api_key:
            logger.warning(
                "%s API key non configurata — le chiamate LLM falliranno.",
                self.provider_name,
            )

    def complete_json(self, system_prompt: str, user_prompt: str) -> Any:
        """Send a prompt expecting a JSON response. Returns parsed dict/list or {}."""
        text = self._call_api(system_prompt, user_prompt, json_mode=True)
        return parse_json_text(text)

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        """Send a prompt expecting a free-text response."""
        return self._call_api(system_prompt, user_prompt)

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
    ) -> str:
        if not self.api_key:
            logger.error("Chiamata %s senza API key configurata.", self.provider_name)
            return ""

        url = f"{self.base_url.rstrip('/')}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        last_error = None
        for attempt in range(1 + MAX_RETRIES):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=60)

                # Retry on transient HTTP errors
                if resp.status_code in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else 2.0
                    logger.warning(
                        "%s API %d, retry %d/%d in %.1fs",
                        self.provider_name, resp.status_code,
                        attempt + 1, MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0]["message"]["content"]
                logger.warning("Risposta %s senza choices: %s", self.provider_name, data)
                return ""

            except requests.exceptions.Timeout:
                last_error = "Timeout"
                if attempt < MAX_RETRIES:
                    wait = RETRY_BACKOFF[attempt] if attempt < len(RETRY_BACKOFF) else 2.0
                    logger.warning(
                        "%s timeout, retry %d/%d in %.1fs",
                        self.provider_name, attempt + 1, MAX_RETRIES, wait,
                    )
                    time.sleep(wait)
                    continue
                logger.error("Timeout nella chiamata a %s API (tutti i retry esauriti).", self.provider_name)
                return ""

            except requests.exceptions.RequestException as exc:
                last_error = str(exc)
                logger.error("Errore chiamata %s: %s", self.provider_name, exc)
                return ""

        logger.error("%s API fallita dopo %d tentativi: %s", self.provider_name, MAX_RETRIES + 1, last_error)
        return ""
