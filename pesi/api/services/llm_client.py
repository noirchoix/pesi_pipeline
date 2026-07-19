from __future__ import annotations

import json
from typing import Any

import requests

from pesi.api.config import ApiSettings
from pesi.api.services.json_safe import to_json_safe


class LLMUnavailable(RuntimeError):
    pass


class DeepSeekClient:
    """Server-side DeepSeek JSON client with deterministic fallback."""

    def __init__(self, settings: ApiSettings):
        self.settings = settings
        self.enabled = bool(
            settings.ai_enabled
            and settings.ai_provider.strip().casefold() == "deepseek"
            and settings.deepseek_api_key
        )
        self.base_url = settings.deepseek_base_url.rstrip("/")
        self.model = settings.deepseek_model
        self.timeout = settings.deepseek_timeout_seconds
        self.max_tokens = settings.deepseek_max_tokens

    def configuration_status(self) -> dict[str, Any]:
        if not self.settings.ai_enabled:
            status = "disabled"
        elif self.settings.ai_provider.strip().casefold() != "deepseek":
            status = "unsupported_provider"
        elif not self.settings.deepseek_api_key:
            status = "missing_api_key"
        else:
            status = "configured"
        return {
            "enabled": self.enabled,
            "status": status,
            "provider": self.settings.ai_provider,
            "model": self.model,
            "base_url": self.base_url,
            "env_file_loaded": str(self.settings.env_file) if self.settings.env_file else None,
        }

    def complete_json(self, *, system: str, user: str, fallback: dict[str, Any]) -> dict[str, Any]:
        safe_fallback = to_json_safe(fallback)
        if not self.enabled:
            reason = self.configuration_status()["status"]
            return {**safe_fallback, "ai_source": "deterministic_fallback", "ai_status": reason}

        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.15,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.deepseek_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = requests.post(
                url,
                headers=headers,
                data=json.dumps(to_json_safe(payload), allow_nan=False),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            parsed = json.loads(content) if isinstance(content, str) else content
            if not isinstance(parsed, dict):
                raise ValueError("DeepSeek response was not a JSON object")
            parsed = to_json_safe(parsed)
            parsed.setdefault("ai_source", "deepseek")
            parsed.setdefault("ai_status", "generated")
            return parsed
        except Exception as exc:
            out = dict(safe_fallback)
            out["ai_source"] = "deterministic_fallback"
            out["ai_status"] = f"model_error:{type(exc).__name__}"
            return out
