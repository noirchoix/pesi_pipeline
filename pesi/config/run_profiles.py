from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_RUN_PROFILES: dict[str, dict[str, Any]] = {
    "audit": {
        "uniprot_rows": 300,
        "cazy_rows": 300,
        "plantmet_edges": 300,
        "plantcyc_triples": 300,
        "enzyme_smi_pairs": 300,
    },
    "medium": {
        "uniprot_rows": 10_000,
        "cazy_rows": 25_000,
        "plantmet_edges": 50_000,
        "plantcyc_triples": 50_000,
        "enzyme_smi_pairs": 25_000,
    },
    "large": {
        "uniprot_rows": 100_000,
        "cazy_rows": 250_000,
        "plantmet_edges": 500_000,
        "plantcyc_triples": 500_000,
        "enzyme_smi_pairs": 100_000,
    },
    "full": {
        "uniprot_rows": None,
        "cazy_rows": None,
        "plantmet_edges": None,
        "plantcyc_triples": None,
        "enzyme_smi_pairs": None,
    },
}


def get_run_profile(profile: str = "audit") -> dict[str, Any] | None:
    key = (profile or "audit").lower().strip()
    if key == "full":
        return None
    return DEFAULT_RUN_PROFILES.get(key, DEFAULT_RUN_PROFILES["audit"]).copy()
