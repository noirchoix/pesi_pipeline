from __future__ import annotations

import json
from typing import Any

import requests

from pesi.api.config import ApiSettings


class LLMUnavailable(RuntimeError):
    pass


class DeepSeekClient:
    """Small server-side DeepSeek client for grounded PESI explanations.

    The client is intentionally optional. When credentials are absent or the model
    call fails, callers should return the deterministic artifact-grounded fallback
    instead of blocking the product flow.
    """

    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.enabled = bool(settings.ai_enabled and settings.deepseek_api_key)
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.model = settings.deepseek_model
        self.timeout = settings.deepseek_timeout_seconds

    def complete_json(self, *, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {**fallback, "ai_source": "deterministic_fallback", "ai_status": "not_configured"}

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.15,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content) if isinstance(content, str) else content
            if not isinstance(parsed, dict):
                raise ValueError("DeepSeek response was not a JSON object")
            parsed.setdefault("ai_source", "deepseek")
            parsed.setdefault("ai_status", "generated")
            return parsed
        except Exception as exc:
            out = dict(fallback)
            out["ai_source"] = "deterministic_fallback"
            out["ai_status"] = f"model_error: {type(exc).__name__}"
            return out
