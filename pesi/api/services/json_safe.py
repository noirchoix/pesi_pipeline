from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


def to_json_safe(value: Any, *, _depth: int = 0, max_depth: int = 80) -> Any:
    """Return a JSON-serializable structure with all non-finite numbers removed.

    PESI artifacts are produced through pandas/numpy pipelines, so NaN and
    +/-Infinity can appear inside deeply nested report/evidence structures.
    Starlette intentionally rejects those values. This function normalizes the
    complete payload before API serialization, DeepSeek prompt construction,
    and HTML technical-appendix rendering.
    """
    if _depth > max_depth:
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)

    # numpy scalar values and similar wrappers expose item().
    item = getattr(value, "item", None)
    if callable(item):
        try:
            unwrapped = item()
            if unwrapped is not value:
                return to_json_safe(unwrapped, _depth=_depth + 1, max_depth=max_depth)
        except Exception:
            pass

    if hasattr(value, "model_dump"):
        try:
            return to_json_safe(value.model_dump(mode="json"), _depth=_depth + 1, max_depth=max_depth)
        except Exception:
            try:
                return to_json_safe(value.model_dump(), _depth=_depth + 1, max_depth=max_depth)
            except Exception:
                pass
    if is_dataclass(value):
        return to_json_safe(asdict(value), _depth=_depth + 1, max_depth=max_depth)
    if isinstance(value, Mapping):
        return {
            str(key): to_json_safe(item_value, _depth=_depth + 1, max_depth=max_depth)
            for key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [to_json_safe(item_value, _depth=_depth + 1, max_depth=max_depth) for item_value in value]
    if isinstance(value, set):
        return [to_json_safe(item_value, _depth=_depth + 1, max_depth=max_depth) for item_value in sorted(value, key=str)]

    # Last-resort conversion keeps audit metadata readable rather than failing
    # an otherwise valid report response.
    return str(value)
