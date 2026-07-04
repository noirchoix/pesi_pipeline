from __future__ import annotations

import glob
import json
import math
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pesi.core.utils import ensure_dir, normalize_columns, open_maybe_gzip, split_semicolon, to_number, write_json

PLANT_KINGDOM_MARKERS = ["viridiplantae", "streptophyta", "embryophyta", "tracheophyta", "magnoliopsida", "liliopsida"]

CORE_STAGE_ANCHORS = [
    {"stage": "germination", "enzyme_name": "alpha-amylase", "enzyme_family": "amylase", "target_class": "reserve_mobilization", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "germination", "enzyme_name": "cellulase", "enzyme_family": "CAZy", "target_class": "cell_wall_remodeling", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "seedling_emergence", "enzyme_name": "acetolactate synthase", "enzyme_family": "ALS/AHAS", "target_class": "branched_chain_amino_acid_biosynthesis", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "early_vegetative", "enzyme_name": "EPSP synthase", "enzyme_family": "EPSPS", "target_class": "shikimate_aromatic_amino_acid_biosynthesis", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "early_vegetative", "enzyme_name": "photosystem II", "enzyme_family": "PSII", "target_class": "photosynthesis_electron_transport", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "vegetative_expansion", "enzyme_name": "ribulose bisphosphate carboxylase oxygenase", "enzyme_family": "RuBisCO", "target_class": "carbon_fixation", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "vegetative_expansion", "enzyme_name": "protoporphyrinogen oxidase", "enzyme_family": "PPO", "target_class": "chlorophyll_tetrapyrrole_biosynthesis", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "vegetative_expansion", "enzyme_name": "acetyl-CoA carboxylase", "enzyme_family": "ACCase", "target_class": "fatty_acid_biosynthesis", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "vegetative_expansion", "enzyme_name": "phosphoenolpyruvate carboxylase", "enzyme_family": "PEPC", "target_class": "carbon_concentration_anaplerotic", "evidence_class": "real_evidence", "source": "weed_assignment"},
    {"stage": "stress_response", "enzyme_name": "peroxidase", "enzyme_family": "Peroxidase", "target_class": "oxidative_stress_redox_control", "evidence_class": "real_evidence", "source": "curated_families"},
    {"stage": "specialized_metabolism", "enzyme_name": "cytochrome P450", "enzyme_family": "Cytochrome P450", "target_class": "detoxification_secondary_metabolism", "evidence_class": "real_evidence", "source": "curated_families"},
    {"stage": "specialized_metabolism", "enzyme_name": "UDP glycosyltransferase", "enzyme_family": "UDP glycosyltransferase", "target_class": "glycosylation_detoxification", "evidence_class": "real_evidence", "source": "curated_families"},
    {"stage": "cell_wall_secondary_growth", "enzyme_name": "BAHD acyltransferase", "enzyme_family": "BAHD acyltransferase", "target_class": "phenylpropanoid_acylation", "evidence_class": "real_evidence", "source": "curated_families"},
]


def load_skid(raw: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    path = raw / "skid" / "Main_dataset_v1.xlsx"
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    frames = []
    for sheet, pcol, ptype in [("kcat_dataset", "kcat_value", "kcat"), ("Km_dataset", "Km_value", "Km")]:
        df = pd.read_excel(path, sheet_name=sheet)
        df = normalize_columns(df)
        val_col = pcol.lower()
        if val_col not in df.columns:
            val_col = "kcat_value" if ptype == "kcat" else "km_value"
        df["parameter_type"] = ptype
        df["parameter_value"] = df[val_col].map(to_number) if val_col in df.columns else np.nan
        df["ph"] = df.get("ph", pd.Series([np.nan]*len(df))).map(to_number)
        df["temperature_c"] = df.get("temperature", pd.Series([np.nan]*len(df))).map(to_number)
        df["evidence_class"] = "real_evidence"
        df["source_resource"] = "SKiD Main_dataset_v1.xlsx"
        frames.append(df)
    kinetics = pd.concat(frames, ignore_index=True, sort=False)
    # Kinetic plausibility rules from textbooks: retain raw but flag invalid/missing physical contexts.
    kinetics["kinetic_plausibility"] = np.select(
        [kinetics["parameter_value"].isna(), kinetics["parameter_value"] <= 0, kinetics["ph"].notna() & ((kinetics["ph"] < 0) | (kinetics["ph"] > 14))],
        ["missing_value", "non_positive_parameter", "implausible_pH"],
        default="plausible_or_unchecked",
    )
    # Structure metadata
    struct_cols = [c for c in ["entry_id", "ec_number", "uniprot_id", "protein_file", "site_type", "substrate", "substrate_smiles", "mol_file", "organism_name", "mutant", "mutation"] if c in kinetics.columns]
    structure = kinetics[struct_cols].drop_duplicates() if struct_cols else pd.DataFrame()
    unique_enz = pd.read_excel(path, sheet_name="Unique_enzymes")
    unique_enz = normalize_columns(unique_enz)
    unique_enz["evidence_class"] = "real_evidence"
    unique_enz["source_resource"] = "SKiD Unique_enzymes"
    return kinetics, structure, unique_enz


def load_bkms(raw: Path) -> pd.DataFrame:
    path = raw / "bkms" / "Reactions_BKMS.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, sep="\t", low_memory=False)
    df = normalize_columns(df)
    df["evidence_class"] = "real_evidence"
    df["source_resource"] = "BKMS Reactions"
    return df


def load_uniprot_rhea(raw: Path, max_rows: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    path = raw / "uniprot_rhea" / "cleaned_uniprot_rhea.tsv"
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame()
    df = pd.read_csv(path, sep="\t", nrows=max_rows, low_memory=False)
    df = normalize_columns(df)
    if "ec_number" not in df.columns and "ec_numbers" in df.columns:
        df["ec_number"] = df["ec_numbers"]
    df["sequence_length"] = df.get("sequence", pd.Series([""] * len(df))).fillna("").map(len)
    df["evidence_class"] = "real_evidence"
    df["source_resource"] = "UniProt_Rhea"
    rows = []
    for _, r in df.iterrows():
        ecs = split_semicolon(r.get("ec_number"))
        rheas = split_semicolon(r.get("rhea_id"))
        if not ecs: ecs = [None]
        if not rheas: rheas = [None]
        for ec in ecs:
            for rh in rheas:
                rows.append({"uniprot_id": r.get("entry"), "ec_number": ec, "rhea_id": rh, "sequence_length": r.get("sequence_length"), "evidence_class": "real_evidence", "source_resource": "UniProt_Rhea"})
    mapping = pd.DataFrame(rows)
    return df, mapping


def load_cazy(raw: Path, max_rows: int | None = None) -> pd.DataFrame:
    paths = list((raw / "cazy").glob("*.txt"))
    if not paths:
        return pd.DataFrame()
    path = paths[0]
    cols = ["cazy_family", "kingdom", "organism", "accession", "source_db"]
    df = pd.read_csv(path, sep="\t", names=cols, nrows=max_rows, low_memory=False)
    df["is_plant_like"] = df["kingdom"].fillna("").str.lower().str.contains("viridiplantae|plant") | df["organism"].fillna("").str.lower().str.contains("arabidopsis|zea|oryza|wheat|rice|maize|sorghum|solanum|glycine|vitis")
    df["cazy_class"] = df["cazy_family"].fillna("").str.extract(r"^([A-Za-z]+)")[0]
    df["evidence_class"] = "real_evidence"
    df["source_resource"] = "CAZy"
    return df


def load_plantmetwiki(raw: Path, max_edges: int | None = None) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    base = raw / "plantmetwiki"
    # extraction may have files at base root or nested.
    node_paths = list(base.rglob("nodes.tsv"))
    edge_paths = list(base.rglob("edges.tsv"))
    if not node_paths or not edge_paths:
        return pd.DataFrame(), pd.DataFrame(), {}
    nodes = pd.read_csv(node_paths[0], sep="\t", low_memory=False)
    edges = pd.read_csv(edge_paths[0], sep="\t", nrows=max_edges, low_memory=False)
    nodes = normalize_columns(nodes); edges = normalize_columns(edges)
    nodes["evidence_class"] = "real_evidence"; edges["evidence_class"] = "real_evidence"
    nodes["source_resource"] = "PlantMetWiki"; edges["source_resource"] = "PlantMetWiki"
    stats = {"node_rows": len(nodes), "edge_rows_loaded": len(edges)}
    for p in ["heterodata.pt", "splits.pt", "splits_taxa.pt", "splits_pathway.pt", "embeddings_metabolite.pt", "embeddings_protein.pt", "embeddings_gene.pt"]:
        found = list(base.rglob(p))
        stats[p] = str(found[0]) if found else None
    return nodes, edges, stats


def load_plantcyc_summary(raw: Path, max_triples: int = 100000) -> tuple[pd.DataFrame, pd.DataFrame]:
    base = raw / "plantcyc"
    files = list(base.rglob("*.ttl")) + list(base.rglob("*.ttl.gz"))
    records = []
    concept_rows = []
    triple_re = re.compile(r"^\s*([^#\s][^\s]*)\s+([^\s]+)\s+(.+?)\s*\.\s*$")
    for f in files:
        count = 0
        try:
            with open_maybe_gzip(f, "rt") as fh:
                for line in fh:
                    if line.startswith("#") or not line.strip():
                        continue
                    m = triple_re.match(line)
                    if not m:
                        continue
                    count += 1
                    if len(concept_rows) < max_triples:
                        s, p, o = m.groups()
                        concept_rows.append({"subject": s[:500], "predicate": p[:250], "object": o[:500], "evidence_class": "real_evidence", "source_resource": "PlantCyc_RDF"})
                    if count >= max_triples and f.name.startswith("all-"):
                        break
        except Exception as e:
            records.append({"file": str(f), "triple_count_loaded": count, "error": repr(e)})
            continue
        records.append({"file": str(f), "triple_count_loaded": count, "error": ""})
    return pd.DataFrame(records), pd.DataFrame(concept_rows)


def load_fooddb(raw: Path) -> dict[str, pd.DataFrame]:
    base = raw / "fooddb"
    # zip extraction creates raw/fooddb/food_chemistry/...
    candidates = list(base.rglob("curated/v1"))
    curated = candidates[0] if candidates else None
    out: dict[str, pd.DataFrame] = {}
    if curated:
        for name in ["compound_descriptors", "compound_enzyme_edges", "compound_pathway_edges", "food_compound_edges", "compound_idf"]:
            p = curated / f"{name}.parquet"
            if p.exists():
                try:
                    # Parquet tables such as food_compound_edges can contain millions of rows.
                    # Read bounded batches for audit/runtime while preserving source row counts in registry reports.
                    try:
                        import pyarrow.parquet as pq
                        pf = pq.ParquetFile(p)
                        limit = 200000 if name == "food_compound_edges" else 120000
                        batches = []
                        total = 0
                        for batch in pf.iter_batches(batch_size=min(limit, 50000)):
                            batches.append(batch.to_pandas())
                            total += batch.num_rows
                            if total >= limit:
                                break
                        df = pd.concat(batches, ignore_index=True).head(limit) if batches else pd.DataFrame()
                        df.attrs["source_total_rows"] = pf.metadata.num_rows if pf.metadata else None
                    except Exception:
                        df = pd.read_parquet(p).head(200000 if name == "food_compound_edges" else 120000)
                    df = normalize_columns(df)
                    df["evidence_class"] = "real_evidence"
                    df["source_resource"] = "FoodDB_curated"
                    out[name] = df
                except Exception as e:
                    out[name] = pd.DataFrame([{"load_error": repr(e), "evidence_class": "unsupported", "source_resource": "FoodDB_curated"}])
    duckdb_paths = list(base.rglob("fooddb.duckdb"))
    if duckdb_paths:
        try:
            import duckdb
            con = duckdb.connect(str(duckdb_paths[0]), read_only=True)
            tables = con.sql("SHOW TABLES").fetchdf()
            out["duckdb_tables"] = tables
            # Try known useful tables, but tolerate schema differences.
            for t in tables.iloc[:, 0].astype(str).head(20):
                try:
                    df = con.sql(f"SELECT * FROM {t} LIMIT 10000").fetchdf()
                    df = normalize_columns(df)
                    df["evidence_class"] = "real_evidence"
                    df["source_resource"] = f"FoodDB_duckdb:{t}"
                    out[f"duckdb_{t}"] = df
                except Exception:
                    pass
            con.close()
        except Exception as e:
            out["duckdb_error"] = pd.DataFrame([{"load_error": repr(e)}])
    return out

def load_curated_families(raw: Path) -> pd.DataFrame:
    """
    Load curated enzyme-family workbooks into one canonical table.

    Canonical classifier/KG label:
    - curated_family

    Important:
    - The workbook column `Family` / `family` is taxonomic family.
    - It must be preserved as `family`, but never used as the enzyme-family label.
    - `curated_family` is derived from the workbook filename.

    Preferred sheet policy:
    - Prefer NewIDs, then ID, then FULLNAME, then KINGDOM, then FLAG.
    - This avoids double-counting intermediate QC sheets.
    """
    folder = raw / "curated_families"

    canonical_columns = [
        "title",
        "doi",
        "species",
        "family",
        "kingdom",
        "enzyme_common_name",
        "enzyme_full_name",
        "genbank",
        "uniprot_id",
        "alt_id",
        "substrate",
        "product",
        "flag",
        "curated_family",
        "source_sheet",
        "source_resource",
        "evidence_class",
    ]

    if not folder.exists():
        return pd.DataFrame(columns=canonical_columns)

    def _norm_col(value: Any) -> str:
        return (
            str(value)
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
            .replace("?", "")
            .replace("#", "")
        )

    def _dedupe_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure every dataframe has unique column names before pd.concat.

        Excel sheets can contain repeated/blank columns, and normalization can also
        collapse distinct headers into the same key. Pandas concat requires unique
        column labels per frame.
        """
        if df is None or len(df.columns) == 0:
            return df

        counts: dict[str, int] = {}
        new_cols: list[str] = []

        for col in df.columns:
            base = _norm_col(col)

            if base in {"", "nan", "none", "null"}:
                base = "unnamed"

            if base not in counts:
                counts[base] = 0
                new_cols.append(base)
            else:
                counts[base] += 1
                new_cols.append(f"{base}__dup{counts[base]}")

        out = df.copy()
        out.columns = new_cols
        return out

    def _canonical_family_name(path: Path) -> str:
        name = path.stem
        name = re.sub(r"_?minimally_?curated_?set$", "", name, flags=re.IGNORECASE)
        name = name.replace("_", " ").replace("-", " ").strip()
        return name or path.stem

    def _choose_sheet(sheet_names: list[str]) -> str | None:
        if not sheet_names:
            return None

        lowered = {str(s).strip().lower(): s for s in sheet_names}

        preferred_exact = [
            "newids",
            "id",
            "fullname",
            "kingdom",
            "flag",
        ]

        for key in preferred_exact:
            if key in lowered:
                return lowered[key]

        # Fall back to the first non-QC, non-legend sheet.
        for sh in sheet_names:
            s = str(sh).strip().lower()
            if s in {"legend", "hallucinations"}:
                continue
            return sh

        return None

    def _read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
        df = pd.read_excel(path, sheet_name=sheet_name)

        if df is None or len(df) == 0:
            return pd.DataFrame()

        df = df.copy()
        df = _dedupe_columns(df)

        rename_map = {
            "original_order": "original_order",
            "unnamed:_0": "unnamed_0",
            "enzyme": "enzyme_full_name",
            "enzyme_name": "enzyme_full_name",
            "protein": "enzyme_full_name",
            "protein_name": "enzyme_full_name",
            "organism": "species",
            "organism_name": "species",
            "plant_species": "species",
            "substrates": "substrate",
            "products": "product",
            "flag_keep": "flag_keep",
            "kingdom_keep": "kingdom_keep",
            "kingdom_keep_": "kingdom_keep",
            "fullname_keep": "fullname_keep",
            "fullname_keep_": "fullname_keep",
            "full_name_include": "fullname_include",
            "fullname_include": "fullname_include",
            "id_presence": "id_presence",
            "subst_presence": "subst_presence",
            "substrate": "substrate",
            "product": "product",
            "uniprot_accessions": "uniprot_accessions",
            "pfam_domains": "pfam_domains",
        }

        df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

        # Renaming can create duplicate canonical names, so dedupe again.
        df = _dedupe_columns(df)

        for col in [
            "title",
            "doi",
            "species",
            "family",
            "kingdom",
            "enzyme_common_name",
            "enzyme_full_name",
            "genbank",
            "uniprot_id",
            "alt_id",
            "substrate",
            "product",
            "flag",
        ]:
            if col not in df.columns:
                df[col] = np.nan

        biological_cols = [
            "title",
            "species",
            "enzyme_common_name",
            "enzyme_full_name",
            "substrate",
            "product",
            "uniprot_id",
            "genbank",
            "alt_id",
        ]

        existing_bio_cols = [c for c in biological_cols if c in df.columns]

        if existing_bio_cols:
            has_content = (
                df[existing_bio_cols]
                .fillna("")
                .astype(str)
                .agg(" ".join, axis=1)
                .str.strip()
                .str.len()
                .gt(0)
            )
            df = df.loc[has_content].copy()

        return df

    frames: list[pd.DataFrame] = []

    for path in sorted(folder.glob("*.xlsx")):
        curated_family = _canonical_family_name(path)

        try:
            xl = pd.ExcelFile(path)
            selected_sheet = _choose_sheet(xl.sheet_names)

            if selected_sheet is None:
                frames.append(pd.DataFrame([{
                    "curated_family": curated_family,
                    "source_sheet": np.nan,
                    "source_resource": path.name,
                    "evidence_class": "unsupported",
                    "load_error": "no_readable_sheet",
                }]))
                continue

            df = _read_sheet(path, selected_sheet)

            if df is None or len(df) == 0:
                frames.append(pd.DataFrame([{
                    "curated_family": curated_family,
                    "source_sheet": selected_sheet,
                    "source_resource": path.name,
                    "evidence_class": "unsupported",
                    "load_error": "selected_sheet_empty_after_content_filter",
                }]))
                continue

            # Lock enzyme-family label from workbook filename.
            # Do not derive this from workbook `family`; that is taxonomy.
            df["curated_family"] = curated_family
            df["source_sheet"] = str(selected_sheet)
            df["source_resource"] = path.name
            df["evidence_class"] = "real_evidence"

            frames.append(_dedupe_columns(df))

        except Exception as e:
            frames.append(pd.DataFrame([{
                "curated_family": curated_family,
                "source_sheet": np.nan,
                "source_resource": path.name,
                "evidence_class": "unsupported",
                "load_error": repr(e),
            }]))

    frames = [_dedupe_columns(f) for f in frames if f is not None and len(f) > 0]

    if not frames:
        return pd.DataFrame(columns=canonical_columns)

    out = pd.concat(frames, ignore_index=True, sort=False)
    out = _dedupe_columns(out)

    for col in canonical_columns:
        if col not in out.columns:
            out[col] = np.nan

    out["curated_family"] = (
        out["curated_family"]
        .astype(str)
        .str.strip()
        .replace({"": np.nan, "nan": np.nan, "None": np.nan, "null": np.nan})
    )

    out = out.dropna(subset=["curated_family"]).copy()

    return out

def load_enzyme_datasets(raw: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = raw / "enzyme_datasets"
    files = list(root.rglob("data/processed/*.csv"))
    summaries = []
    samples = []
    for f in files:
        try:
            df = pd.read_csv(f, nrows=2000, low_memory=False)
            dfn = normalize_columns(df)
            summaries.append({"dataset": f.name, "path": str(f), "columns": list(dfn.columns), "sample_rows": len(dfn), "evidence_class": "real_evidence", "source_resource": "enzyme-datasets-main"})
            dfn["dataset"] = f.name
            dfn["source_resource"] = "enzyme-datasets-main"
            dfn["evidence_class"] = "real_evidence"
            samples.append(dfn.head(500))
        except Exception as e:
            summaries.append({"dataset": f.name, "path": str(f), "error": repr(e), "evidence_class": "unsupported", "source_resource": "enzyme-datasets-main"})
    return pd.DataFrame(summaries), (pd.concat(samples, ignore_index=True, sort=False) if samples else pd.DataFrame())


def load_enzyme_smi(raw: Path, max_pairs: int = 20000) -> pd.DataFrame:
    base = raw / "enzyme_smi"
    files = list(base.rglob("positive_*seq_smi.pt"))
    frames = []
    for f in files:
        try:
            import torch
            obj = torch.load(f, map_location="cpu", weights_only=False)
            rows = []
            for i, (k, v) in enumerate(obj.items() if isinstance(obj, dict) else enumerate(obj)):
                if i >= max_pairs:
                    break
                if isinstance(v, (tuple, list)) and len(v) >= 2:
                    smi, seq = v[0], v[1]
                else:
                    continue
                rows.append({"pair_id": k, "smiles": str(smi), "sequence": str(seq), "split_file": f.name, "label": 1, "evidence_class": "real_evidence", "source_resource": "enzyme_smi_split"})
            frames.append(pd.DataFrame(rows))
        except Exception as e:
            frames.append(pd.DataFrame([{"load_error": repr(e), "split_file": f.name, "evidence_class": "unsupported", "source_resource": "enzyme_smi_split"}]))
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def load_enzymeflow_assets(raw: Path) -> dict[str, pd.DataFrame]:
    base = raw / "enzymeflow"
    out = {}
    for name in ["metadata.csv", "kdvalue.csv"]:
        found = list(base.rglob(name))
        if found:
            try:
                df = pd.read_csv(found[0], low_memory=False)
                df = normalize_columns(df)
                df["evidence_class"] = "real_evidence"
                df["source_resource"] = "EnzymeFlow"
                out[name.replace(".csv", "")] = df
            except Exception as e:
                out[name] = pd.DataFrame([{"load_error": repr(e)}])
    ppaths = list(base.rglob("*.pdb"))[:100]
    out["pdb_assets"] = pd.DataFrame([{"path": str(p), "pdb_id": p.stem.split("_")[0], "size_bytes": p.stat().st_size, "evidence_class": "real_evidence", "source_resource": "EnzymeFlow"} for p in ppaths])
    return out


def load_reactzyme_assets(raw: Path) -> dict[str, pd.DataFrame]:
    base = raw / "reactzyme"
    files = list(base.rglob("*.py")) + list(base.rglob("README.md"))
    manifest = []
    for f in files:
        manifest.append({"path": str(f), "filename": f.name, "size_bytes": f.stat().st_size, "evidence_class": "method_asset", "source_resource": "ReactZyme"})
    return {"manifest": pd.DataFrame(manifest)}


def load_vocab_assets(raw: Path) -> dict[str, Any]:
    base = raw / "vocabs"
    out: dict[str, Any] = {}
    p = base / "deepchem_vocab.txt"
    if p.exists():
        toks = [line.strip() for line in p.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]
        out["deepchem_vocab"] = {"token_count": len(toks), "tokens_sample": toks[:50]}
    mp = base / "molecule_vocab.pkl"
    if mp.exists():
        try:
            import pickle
            with open(mp, "rb") as f:
                obj = pickle.load(f)
            out["molecule_vocab"] = {"type": str(type(obj)), "length": len(obj) if hasattr(obj, "__len__") else None, "sample": str(obj)[:500]}
        except Exception as e:
            out["molecule_vocab"] = {"load_error": repr(e)}
    return out


def load_sabio_cache(raw: Path) -> pd.DataFrame:
    base = raw / "sabio_cache"
    files = list(base.glob("*.jsonl"))
    rows = []
    for f in files:
        with open(f, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        obj["source_file"] = f.name
                        rows.append(obj)
                except Exception:
                    continue
    if not rows:
        return pd.DataFrame()
    df = pd.json_normalize(rows, sep="_")
    df["evidence_class"] = "real_evidence"
    df["source_resource"] = "SABIO-RK cache"
    return df


def load_all(raw_dir: str | Path, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = Path(raw_dir)
    limits = limits or {}
    data: dict[str, Any] = {}
    data["skid_kinetics"], data["skid_structures"], data["skid_unique_enzymes"] = load_skid(raw)
    data["bkms"] = load_bkms(raw)
    data["uniprot"], data["uniprot_rhea_map"] = load_uniprot_rhea(raw, max_rows=limits.get("uniprot_rows"))
    data["cazy"] = load_cazy(raw, max_rows=limits.get("cazy_rows"))
    data["plantmet_nodes"], data["plantmet_edges"], data["plantmet_stats"] = load_plantmetwiki(raw, max_edges=limits.get("plantmet_edges"))
    data["plantcyc_files"], data["plantcyc_triples"] = load_plantcyc_summary(raw, max_triples=limits.get("plantcyc_triples", 100000))
    data["fooddb"] = load_fooddb(raw)
    data["curated_families"] = load_curated_families(raw)
    data["enzyme_dataset_summaries"], data["enzyme_dataset_samples"] = load_enzyme_datasets(raw)
    data["enzyme_smi_pairs"] = load_enzyme_smi(raw, max_pairs=limits.get("enzyme_smi_pairs", 20000))
    data["enzymeflow"] = load_enzymeflow_assets(raw)
    data["reactzyme"] = load_reactzyme_assets(raw)
    data["vocabs"] = load_vocab_assets(raw)
    data["sabio_cache"] = load_sabio_cache(raw)
    data["stage_anchors"] = pd.DataFrame(CORE_STAGE_ANCHORS)
    return data
