from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

import numpy as np
import pandas as pd


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def file_size(path: str | Path) -> int:
    return Path(path).stat().st_size if Path(path).exists() else 0


def write_json(path: str | Path, data: Any) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def read_json(path: str | Path, default: Any = None) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def safe_read_csv(path_or_buf: Any, sep: str | None = None, nrows: int | None = None, **kwargs) -> pd.DataFrame:
    if sep is None:
        sep = "\t" if str(path_or_buf).endswith((".tsv", ".txt")) else ","
    return pd.read_csv(path_or_buf, sep=sep, nrows=nrows, low_memory=False, **kwargs)


def normalize_colname(name: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [normalize_colname(c) for c in out.columns]
    return out


def to_number(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (int, float)) and not pd.isna(x):
        return float(x)
    s = str(x).strip()
    if not s or s in {"-----", "nan", "NaN", "None"}:
        return None
    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def split_semicolon(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    return [x.strip() for x in re.split(r"[;|]", str(value)) if x.strip()]


def open_maybe_gzip(path: str | Path, mode: str = "rt"):
    path = Path(path)
    if path.suffix == ".gz":
        return gzip.open(path, mode, encoding=None if "b" in mode else "utf-8", errors="ignore")
    return open(path, mode, encoding=None if "b" in mode else "utf-8", errors="ignore")


def write_df(df: pd.DataFrame, path: str | Path, index: bool = False) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    if path.suffix == ".parquet":
        df.to_parquet(path, index=index)
    else:
        df.to_csv(path, index=index)


def sample_text(path: str | Path, max_chars: int = 2000) -> str:
    try:
        with open_maybe_gzip(path, "rt") as f:
            return f.read(max_chars)
    except Exception:
        return ""


def sqlite_connect(path: str | Path) -> sqlite3.Connection:
    ensure_dir(Path(path).parent)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def df_to_sqlite(conn: sqlite3.Connection, df: pd.DataFrame, table: str, if_exists: str = "replace") -> None:
    # SQLite cannot handle some object/list columns reliably; stringify complex objects.
    if df is None or len(df.columns) == 0:
        return
    clean = df.copy()
    for c in clean.columns:
        if clean[c].map(lambda v: isinstance(v, (list, dict, tuple))).any():
            clean[c] = clean[c].map(lambda v: json.dumps(v, default=str) if isinstance(v, (list, dict, tuple)) else v)
        # SQLite INTEGER is signed 64-bit. Some scientific IDs/checksums exceed this.
        if pd.api.types.is_integer_dtype(clean[c]):
            try:
                max_abs = max(abs(int(clean[c].max(skipna=True))), abs(int(clean[c].min(skipna=True))))
                if max_abs > 9_000_000_000_000_000_000:
                    clean[c] = clean[c].astype(str)
            except Exception:
                clean[c] = clean[c].astype(str)
        elif clean[c].dtype == object:
            # Avoid sqlite adapter issues with numpy scalar/object/timedelta mixtures.
            def _sqlsafe(v):
                try:
                    if pd.isna(v):
                        return None
                except Exception:
                    pass
                if isinstance(v, (str, int, float, bytes)):
                    return v
                if isinstance(v, (np.integer, np.floating)):
                    return str(v)
                return str(v)
            clean[c] = clean[c].map(_sqlsafe)
    try:
        clean.to_sql(table, conn, if_exists=if_exists, index=False, chunksize=10000)
    except OverflowError:
        clean = clean.astype(str).replace({"nan": None, "NaN": None, "None": None})
        clean.to_sql(table, conn, if_exists=if_exists, index=False, chunksize=10000)


def count_rows_csv(path: str | Path, sep: str = "\t") -> int:
    n = 0
    with open_maybe_gzip(path, "rt") as f:
        for _ in f:
            n += 1
    return max(0, n - 1)


def zip_list(path: str | Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        return z.namelist()


def tar_list(path: str | Path) -> list[str]:
    with tarfile.open(path, "r:*") as t:
        return t.getnames()
