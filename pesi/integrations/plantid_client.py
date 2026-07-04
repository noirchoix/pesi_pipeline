from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import requests


class PlantIdClient:
    """Minimal Plant.id v3 adapter.

    API key is read from PLANT_ID_API_KEY unless passed explicitly. This adapter only
    performs identification and returns raw API JSON; downstream PESI logic turns taxa
    suggestions into field-scenario context. It does not store API keys in project files.
    """

    def __init__(self, api_key: str | None = None, base_url: str = "https://plant.id/api/v3") -> None:
        self.api_key = api_key or os.getenv("PLANT_ID_API_KEY")
        self.base_url = base_url.rstrip("/")
        if not self.api_key:
            raise ValueError("Plant.id API key missing. Set PLANT_ID_API_KEY or pass api_key explicitly.")

    def _headers(self) -> dict[str, str]:
        return {"Api-Key": self.api_key, "Content-Type": "application/json"}

    @staticmethod
    def encode_image(path: str | Path) -> str:
        p = Path(path)
        return base64.b64encode(p.read_bytes()).decode("utf-8")

    def identify(
        self,
        images: list[str],
        latitude: float | None = None,
        longitude: float | None = None,
        similar_images: bool = False,
        classification_level: str = "species",
        details: list[str] | None = None,
        health: str | None = None,
        timeout: int = 45,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "images": images,
            "similar_images": similar_images,
            "classification_level": classification_level,
        }
        if latitude is not None:
            payload["latitude"] = latitude
        if longitude is not None:
            payload["longitude"] = longitude
        if health:
            payload["health"] = health
        if details:
            payload["details"] = details
        r = requests.post(f"{self.base_url}/identification", headers=self._headers(), json=payload, timeout=timeout)
        r.raise_for_status()
        return r.json()


def suggestions_to_taxa(result: dict[str, Any], min_probability: float = 0.70) -> list[dict[str, Any]]:
    suggestions = (((result or {}).get("result") or {}).get("classification") or {}).get("suggestions", [])
    taxa = []
    for s in suggestions:
        prob = s.get("probability")
        if prob is not None and float(prob) < min_probability:
            continue
        taxa.append({
            "scientific_name": s.get("name"),
            "probability": prob,
            "source": "Plant.id v3",
            "raw": s,
        })
    return taxa
