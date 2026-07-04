from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable

import requests

from pesi.core.utils import ensure_dir, write_json

BASE_URL = "https://sabiork.h-its.org/export-api/sabio"


def fetch_kinlaw_entries(raw_dir: str | Path, queries: list[str], page_size: int = 100, max_pages: int = 2, sleep_s: float = 1.05) -> dict:
    """Fetch SABIO-RK kinetic law entries into a local JSONL cache.

    Respects the documented public limit by defaulting to approximately one request/sec.
    """
    cache = ensure_dir(Path(raw_dir) / "sabio_cache")
    out_path = cache / "kinlaw_entries.jsonl"
    manifest = {"base_url": BASE_URL, "queries": queries, "page_size": page_size, "max_pages": max_pages, "requests": []}
    total = 0
    with open(out_path, "a", encoding="utf-8") as out:
        for q in queries:
            for page in range(1, max_pages + 1):
                url = f"{BASE_URL}/kinlaw-entry/json"
                params = {"q": q, "page": page, "pageSize": min(page_size, 1000)}
                started = time.time()
                try:
                    r = requests.get(url, params=params, timeout=30)
                    status = r.status_code
                    if status == 429:
                        time.sleep(60)
                        r = requests.get(url, params=params, timeout=30)
                        status = r.status_code
                    r.raise_for_status()
                    payload = r.json()
                    data = payload.get("data", []) if isinstance(payload, dict) else []
                    for entry in data:
                        out.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    total += len(data)
                    manifest["requests"].append({"q": q, "page": page, "status": status, "rows": len(data), "elapsed_s": time.time() - started})
                    if not data:
                        break
                except Exception as e:
                    manifest["requests"].append({"q": q, "page": page, "status": "error", "error": repr(e)})
                    break
                time.sleep(max(0.0, sleep_s))
    manifest["total_rows_written"] = total
    write_json(cache / "query_manifest.json", manifest)
    return manifest
