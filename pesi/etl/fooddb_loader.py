from __future__ import annotations

import json
import os
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from pesi.core.utils import ensure_dir, write_json

FOOD_SOURCE_CAVEAT = (
    "Food/source occurrence is contextual evidence only. It does not establish extractability, "
    "dose, efficacy, crop safety, formulation suitability, or field-use readiness."
)


@dataclass(frozen=True)
class FoodChemistryPaths:
    root: Path
    duckdb_path: Path | None
    curated_dir: Path | None

    @property
    def available(self) -> bool:
        return bool(self.duckdb_path and self.duckdb_path.exists())


def discover_food_chemistry(raw_dir: str | Path) -> FoodChemistryPaths:
    """Discover the supplied FoodDB-derived chemistry bundle without assuming one extraction layout."""
    raw = Path(raw_dir)
    candidates: list[Path] = []
    override = os.getenv("PESI_FOOD_CHEMISTRY_DIR", "").strip()
    if override:
        configured = Path(override)
        candidates.extend([configured, raw / configured] if not configured.is_absolute() else [configured])
    candidates.extend([
        raw / "food_chemistry",
        raw / "fooddb" / "food_chemistry",
        raw / "fooddb",
        raw,
    ])
    # Preserve order while avoiding duplicate filesystem checks.
    candidates = list(dict.fromkeys(candidate.resolve() if candidate.exists() else candidate for candidate in candidates))
    root: Path | None = None
    for candidate in candidates:
        if candidate.exists() and (
            (candidate / "staging" / "fooddb.duckdb").exists()
            or (candidate / "curated" / "v1").exists()
        ):
            root = candidate
            break
    if root is None:
        duck_hits = list(raw.rglob("fooddb.duckdb")) if raw.exists() else []
        root = duck_hits[0].parent.parent if duck_hits else raw / "food_chemistry"
    duckdb_path = root / "staging" / "fooddb.duckdb"
    if not duckdb_path.exists():
        hits = list(root.rglob("fooddb.duckdb")) if root.exists() else []
        duckdb_path = hits[0] if hits else None
    curated_dir = root / "curated" / "v1"
    if not curated_dir.exists():
        hits = list(root.rglob("curated/v1")) if root.exists() else []
        curated_dir = hits[0] if hits else None
    return FoodChemistryPaths(root=root, duckdb_path=duckdb_path, curated_dir=curated_dir)


def normalize_compound_name(value: Any) -> str:
    text = "" if value is None else str(value)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower().replace("alpha", " alpha ").replace("beta", " beta ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _safe_float(value: Any) -> float | None:
    try:
        val = float(value)
        return None if pd.isna(val) else val
    except Exception:
        return None


def _structure_identifiers(smiles: Any) -> tuple[str | None, str | None]:
    text = "" if smiles is None else str(smiles).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None, None
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem import inchi

        RDLogger.DisableLog("rdApp.*")
        mol = Chem.MolFromSmiles(text)
        if mol is None:
            return None, None
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        key = inchi.MolToInchiKey(mol)
        return canonical or None, key or None
    except Exception:
        return None, None


def _looks_like_smiles(value: Any) -> bool:
    text = "" if value is None else str(value).strip()
    return bool(text and any(token in text for token in ("(", ")", "=", "[", "]", "#")))


class FoodDBMapper:
    """Identifier-first mapping from PESI compounds to FoodDB compounds and food occurrence evidence."""

    def __init__(self, raw_dir: str | Path):
        self.paths = discover_food_chemistry(raw_dir)

    def inventory(self) -> dict[str, Any]:
        manifest: dict[str, Any] = {
            "status": "available" if self.paths.available else "missing",
            "root": str(self.paths.root),
            "duckdb_path": str(self.paths.duckdb_path) if self.paths.duckdb_path else None,
            "curated_dir": str(self.paths.curated_dir) if self.paths.curated_dir else None,
            "files": {},
        }
        if self.paths.curated_dir and self.paths.curated_dir.exists():
            for path in sorted(self.paths.curated_dir.glob("*")):
                if path.is_file():
                    manifest["files"][path.name] = {"size_bytes": path.stat().st_size}
            feature_manifest = self.paths.curated_dir / "feature_manifest.json"
            if feature_manifest.exists():
                try:
                    feature_data = json.loads(feature_manifest.read_text(encoding="utf-8"))
                    if isinstance(feature_data, dict):
                        def display_path(path: Path | None) -> str | None:
                            if path is None:
                                return None
                            try:
                                return str(path.resolve().relative_to(Path.cwd().resolve()))
                            except ValueError:
                                return str(path)

                        feature_data["db_path"] = display_path(self.paths.duckdb_path)
                        feature_data["features_dir"] = display_path(self.paths.curated_dir)
                        for artifact in (feature_data.get("artifacts") or {}).values():
                            if isinstance(artifact, dict) and artifact.get("path"):
                                filename = re.split(r"[\\/]", str(artifact["path"]))[-1]
                                artifact["path"] = display_path((self.paths.curated_dir or self.paths.root) / filename)
                    manifest["feature_manifest"] = feature_data
                except Exception:
                    pass
        return manifest

    def _connect(self):
        if not self.paths.available or self.paths.duckdb_path is None:
            raise FileNotFoundError("Food chemistry staging database was not found under raw/food_chemistry.")
        import duckdb

        return duckdb.connect(str(self.paths.duckdb_path), read_only=True)

    def _lookup_frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        con = self._connect()
        try:
            lookup = con.execute(
                """
                SELECT compound_id, public_id, name,
                       cas_number AS smiles_candidate,
                       inchikey, inchi, kingdom, superklass, klass, subklass
                FROM curated_compound_lookup
                """
            ).fetchdf()
            synonyms = con.execute(
                """
                SELECT TRY_CAST(source_id AS BIGINT) AS compound_id, synonym
                FROM compound_synonym
                WHERE source_type = 'Compound' AND synonym IS NOT NULL
                """
            ).fetchdf()
            occurrence = con.execute(
                """
                SELECT compound_id,
                       COUNT(DISTINCT food_id) AS food_count,
                       SUM(CASE WHEN COALESCE(standard_content, 0) > 0 OR COALESCE(orig_content, 0) > 0 THEN 1 ELSE 0 END) AS quantified_records
                FROM curated_food_compound_content
                GROUP BY compound_id
                """
            ).fetchdf()
        finally:
            con.close()
        lookup["name_key"] = lookup["name"].map(normalize_compound_name)
        synonyms = synonyms.dropna(subset=["compound_id", "synonym"]).copy()
        synonyms["compound_id"] = synonyms["compound_id"].astype(int)
        synonyms["name_key"] = synonyms["synonym"].map(normalize_compound_name)
        return lookup, synonyms, occurrence

    def match_compounds(self, compound_pool: pd.DataFrame) -> pd.DataFrame:
        columns = [
            "pesi_compound_name", "pesi_compound_name_canonical", "pesi_smiles", "pesi_canonical_smiles",
            "pesi_inchikey", "fooddb_compound_id", "fooddb_public_id", "fooddb_compound_name",
            "fooddb_inchikey", "fooddb_kingdom", "fooddb_superclass", "fooddb_class", "fooddb_subclass",
            "match_method", "match_confidence", "match_status", "candidate_count", "candidate_ids_json",
            "food_count", "quantified_record_count", "evidence_class", "source_resource", "mapping_caveat",
        ]
        if compound_pool is None or compound_pool.empty or not self.paths.available:
            return pd.DataFrame(columns=columns)

        lookup, synonyms, occurrence = self._lookup_frames()
        lookup = lookup.merge(occurrence, on="compound_id", how="left")
        lookup["food_count"] = lookup["food_count"].fillna(0).astype(int)
        lookup["quantified_records"] = lookup["quantified_records"].fillna(0).astype(int)
        by_id = lookup.set_index("compound_id", drop=False).to_dict("index")

        exact_ik: dict[str, list[int]] = {}
        connectivity: dict[str, list[int]] = {}
        primary_names: dict[str, list[int]] = {}
        synonym_names: dict[str, list[int]] = {}
        for row in lookup.itertuples(index=False):
            cid = int(row.compound_id)
            if isinstance(row.inchikey, str) and row.inchikey:
                exact_ik.setdefault(row.inchikey, []).append(cid)
                connectivity.setdefault(row.inchikey.split("-")[0], []).append(cid)
            if row.name_key:
                primary_names.setdefault(row.name_key, []).append(cid)
        for row in synonyms.itertuples(index=False):
            if row.name_key:
                synonym_names.setdefault(row.name_key, []).append(int(row.compound_id))

        def resolve(ids: Iterable[int], name_key: str) -> tuple[int | None, list[int]]:
            unique = sorted({int(x) for x in ids if int(x) in by_id})
            if not unique:
                return None, []
            exact_primary = [cid for cid in unique if by_id[cid].get("name_key") == name_key]
            candidates = exact_primary or unique
            candidates.sort(
                key=lambda cid: (
                    int(by_id[cid].get("quantified_records") or 0),
                    int(by_id[cid].get("food_count") or 0),
                ),
                reverse=True,
            )
            return candidates[0], unique

        rows: list[dict[str, Any]] = []
        for raw in compound_pool.to_dict("records"):
            name = str(raw.get("compound_name") or raw.get("compound_id") or "").strip()
            canonical_name = str(raw.get("compound_name_canonical") or name).strip()
            smiles = raw.get("smiles")
            canonical_smiles, inchikey = _structure_identifiers(smiles)
            name_key = normalize_compound_name(canonical_name or name)
            ids: list[int] = []
            method = "unmatched"
            confidence = 0.0
            evidence_class = "no_fooddb_identifier_match"
            if inchikey and inchikey in exact_ik:
                ids = exact_ik[inchikey]
                method, confidence, evidence_class = "inchikey_exact", 1.0, "direct_structure_identifier_match"
            elif inchikey and len(connectivity.get(inchikey.split("-")[0], [])) == 1:
                ids = connectivity[inchikey.split("-")[0]]
                method, confidence, evidence_class = "inchikey_connectivity_unique", 0.9, "structure_connectivity_match"
            elif name_key in primary_names:
                ids = primary_names[name_key]
                method, confidence, evidence_class = "primary_name_exact", 0.94, "exact_lexical_identifier_match"
            elif name_key in synonym_names:
                ids = synonym_names[name_key]
                method, confidence, evidence_class = "synonym_exact", 0.9, "exact_synonym_identifier_match"
            selected, candidates = resolve(ids, name_key)
            if selected is None:
                method = "unmatched"
                confidence = 0.0
                evidence_class = "no_fooddb_identifier_match"
            match = by_id.get(selected, {}) if selected is not None else {}
            status = "matched" if selected is not None and len(candidates) == 1 else "ambiguous" if selected is not None else "unmatched"
            rows.append({
                "pesi_compound_name": name,
                "pesi_compound_name_canonical": canonical_name,
                "pesi_smiles": smiles,
                "pesi_canonical_smiles": canonical_smiles,
                "pesi_inchikey": inchikey,
                "fooddb_compound_id": selected,
                "fooddb_public_id": match.get("public_id"),
                "fooddb_compound_name": match.get("name"),
                "fooddb_inchikey": match.get("inchikey"),
                "fooddb_kingdom": match.get("kingdom"),
                "fooddb_superclass": match.get("superklass"),
                "fooddb_class": match.get("klass"),
                "fooddb_subclass": match.get("subklass"),
                "match_method": method,
                "match_confidence": confidence,
                "match_status": status,
                "candidate_count": len(candidates),
                "candidate_ids_json": _json(candidates),
                "food_count": int(match.get("food_count") or 0),
                "quantified_record_count": int(match.get("quantified_records") or 0),
                "evidence_class": evidence_class,
                "source_resource": "FoodDB-derived food chemistry bundle",
                "mapping_caveat": FOOD_SOURCE_CAVEAT,
            })
        return pd.DataFrame(rows, columns=columns)

    def food_sources(self, matches: pd.DataFrame, top_n_per_compound: int = 30) -> pd.DataFrame:
        columns = [
            "pesi_compound_name", "fooddb_compound_id", "fooddb_public_id", "fooddb_compound_name",
            "food_id", "food_public_id", "food_name", "food_name_scientific", "food_group", "food_subgroup",
            "standard_content", "orig_content", "orig_unit", "preparation_type", "evidence_records",
            "citation", "citation_type", "occurrence_evidence", "source_confidence", "rank",
            "compound_match_method", "compound_match_confidence", "compound_match_status",
            "compound_mapping_evidence_class", "evidence_class", "source_resource", "mapping_caveat",
        ]
        if matches is None or matches.empty or not self.paths.available:
            return pd.DataFrame(columns=columns)
        matched = matches[matches["fooddb_compound_id"].notna()].copy()
        if matched.empty:
            return pd.DataFrame(columns=columns)
        ids = sorted({int(x) for x in matched["fooddb_compound_id"].tolist()})
        id_sql = ",".join(str(x) for x in ids)
        con = self._connect()
        try:
            evidence = con.execute(
                f"""
                SELECT c.compound_id,
                       cl.public_id AS fooddb_public_id,
                       cl.name AS fooddb_compound_name,
                       f.food_id, f.public_id AS food_public_id, f.name AS food_name,
                       f.name_scientific AS food_name_scientific,
                       f.food_group, f.food_subgroup,
                       MAX(c.standard_content) AS standard_content,
                       MAX(c.orig_content) AS orig_content,
                       MIN(c.orig_unit) AS orig_unit,
                       MIN(c.preparation_type) AS preparation_type,
                       COUNT(*) AS evidence_records,
                       MIN(c.citation) AS citation,
                       CASE MAX(
                           CASE UPPER(COALESCE(c.citation_type, ''))
                               WHEN 'EXPERIMENTAL' THEN 4
                               WHEN 'ARTICLE' THEN 3
                               WHEN 'DATABASE' THEN 2
                               WHEN 'MANUAL' THEN 1
                               ELSE 0
                           END
                       )
                           WHEN 4 THEN 'EXPERIMENTAL'
                           WHEN 3 THEN 'ARTICLE'
                           WHEN 2 THEN 'DATABASE'
                           WHEN 1 THEN 'MANUAL'
                           ELSE 'UNKNOWN'
                       END AS citation_type
                FROM curated_food_compound_content c
                JOIN curated_food_lookup f ON f.food_id = c.food_id
                JOIN curated_compound_lookup cl ON cl.compound_id = c.compound_id
                WHERE c.compound_id IN ({id_sql})
                GROUP BY c.compound_id, cl.public_id, cl.name, f.food_id, f.public_id, f.name,
                         f.name_scientific, f.food_group, f.food_subgroup
                """
            ).fetchdf()
        finally:
            con.close()
        if evidence.empty:
            return pd.DataFrame(columns=columns)
        map_cols = matches[[
            "pesi_compound_name", "fooddb_compound_id", "match_method", "match_confidence",
            "match_status", "evidence_class",
        ]].dropna(subset=["fooddb_compound_id"]).copy()
        map_cols = map_cols.rename(columns={
            "match_method": "compound_match_method",
            "match_confidence": "compound_match_confidence",
            "match_status": "compound_match_status",
            "evidence_class": "compound_mapping_evidence_class",
        })
        map_cols["fooddb_compound_id"] = map_cols["fooddb_compound_id"].astype(int)
        evidence = map_cols.merge(evidence, left_on="fooddb_compound_id", right_on="compound_id", how="inner")
        evidence["standard_content"] = pd.to_numeric(evidence["standard_content"], errors="coerce")
        evidence["orig_content"] = pd.to_numeric(evidence["orig_content"], errors="coerce")
        quantified = evidence["standard_content"].fillna(0).gt(0) | evidence["orig_content"].fillna(0).gt(0)
        evidence["occurrence_evidence"] = quantified.map({True: "quantified_occurrence", False: "reported_occurrence"})
        citation = evidence["citation_type"].fillna("").astype(str).str.upper()
        evidence["source_confidence"] = 0.55
        evidence.loc[citation.isin(["DATABASE", "ARTICLE", "EXPERIMENTAL"]), "source_confidence"] = 0.7
        evidence.loc[quantified & citation.eq("DATABASE"), "source_confidence"] = 0.86
        evidence.loc[quantified & citation.eq("ARTICLE"), "source_confidence"] = 0.9
        evidence.loc[quantified & citation.eq("EXPERIMENTAL"), "source_confidence"] = 0.96
        evidence["compound_match_confidence"] = pd.to_numeric(evidence["compound_match_confidence"], errors="coerce").fillna(0.0)
        ambiguity_penalty = evidence["compound_match_status"].astype(str).eq("ambiguous").map({True: 0.8, False: 1.0})
        evidence["source_confidence"] = evidence["source_confidence"] * evidence["compound_match_confidence"] * ambiguity_penalty
        evidence["_quant"] = quantified.astype(int)
        evidence["_content"] = evidence["standard_content"].fillna(evidence["orig_content"]).fillna(-1)
        evidence = evidence.sort_values(
            ["pesi_compound_name", "_quant", "source_confidence", "_content", "evidence_records", "food_id"],
            ascending=[True, False, False, False, False, True],
            kind="mergesort",
        )
        evidence["rank"] = evidence.groupby("pesi_compound_name").cumcount() + 1
        evidence = evidence[evidence["rank"] <= max(1, top_n_per_compound)].copy()
        evidence["evidence_class"] = evidence.apply(
            lambda row: (
                "fooddb_quantified_occurrence_evidence" if row["occurrence_evidence"] == "quantified_occurrence"
                else "fooddb_reported_occurrence_evidence"
            ) + ("_with_ambiguous_compound_mapping" if row["compound_match_status"] == "ambiguous" else ""),
            axis=1,
        )
        evidence["source_resource"] = "FoodDB-derived food chemistry bundle"
        evidence["mapping_caveat"] = FOOD_SOURCE_CAVEAT
        evidence = evidence.drop(columns=["compound_id", "_quant", "_content"], errors="ignore")
        return evidence.reindex(columns=columns)


def _top_source_records(frame: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    cols = [
        "food_id", "food_public_id", "food_name", "food_name_scientific", "food_group", "food_subgroup",
        "standard_content", "orig_content", "orig_unit", "preparation_type", "occurrence_evidence",
        "source_confidence", "citation_type", "evidence_class",
    ]
    records = []
    for row in frame.head(limit).to_dict("records"):
        records.append({key: (None if pd.isna(row.get(key)) else row.get(key)) for key in cols})
    return records


def build_pair_source_context(optimized: pd.DataFrame, sources: pd.DataFrame, max_shared: int = 8) -> tuple[pd.DataFrame, pd.DataFrame]:
    context_columns = [
        "pair_key", "compound_a", "compound_b", "shared_food_count", "shared_quantified_food_count",
        "shared_source_confidence", "shared_foods_json", "compound_a_sources_json", "compound_b_sources_json",
        "source_context_status", "evidence_class", "source_resource", "mapping_caveat",
    ]
    evidence_columns = [
        "pair_key", "compound_a", "compound_b", "food_id", "food_public_id", "food_name",
        "food_name_scientific", "food_group", "food_subgroup", "compound_a_occurrence_evidence",
        "compound_b_occurrence_evidence", "compound_a_source_confidence", "compound_b_source_confidence",
        "shared_source_confidence", "evidence_class", "source_resource", "mapping_caveat",
    ]
    if optimized is None or optimized.empty:
        return pd.DataFrame(columns=context_columns), pd.DataFrame(columns=evidence_columns)
    source_groups = {name: group.copy() for name, group in sources.groupby("pesi_compound_name")} if sources is not None and not sources.empty else {}
    pairs = optimized[["compound_a", "compound_b"]].dropna().drop_duplicates().copy()
    pairs["pair_key"] = pairs.apply(lambda r: "||".join(sorted([str(r["compound_a"]), str(r["compound_b"])])), axis=1)
    context_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    for pair in pairs.to_dict("records"):
        a, b, key = str(pair["compound_a"]), str(pair["compound_b"]), str(pair["pair_key"])
        a_src = source_groups.get(a, pd.DataFrame())
        b_src = source_groups.get(b, pd.DataFrame())
        if not a_src.empty and not b_src.empty:
            shared = a_src.merge(b_src, on="food_id", suffixes=("_a", "_b"))
        else:
            shared = pd.DataFrame()
        shared_records: list[dict[str, Any]] = []
        if not shared.empty:
            shared["shared_source_confidence"] = shared[["source_confidence_a", "source_confidence_b"]].min(axis=1)
            shared["_quant"] = (
                shared["occurrence_evidence_a"].eq("quantified_occurrence")
                & shared["occurrence_evidence_b"].eq("quantified_occurrence")
            ).astype(int)
            shared = shared.sort_values(["_quant", "shared_source_confidence"], ascending=[False, False], kind="mergesort")
            for row in shared.head(max_shared).to_dict("records"):
                record = {
                    "food_id": row.get("food_id"),
                    "food_public_id": row.get("food_public_id_a") or row.get("food_public_id_b"),
                    "food_name": row.get("food_name_a") or row.get("food_name_b"),
                    "food_name_scientific": row.get("food_name_scientific_a") or row.get("food_name_scientific_b"),
                    "food_group": row.get("food_group_a") or row.get("food_group_b"),
                    "food_subgroup": row.get("food_subgroup_a") or row.get("food_subgroup_b"),
                    "compound_a_occurrence_evidence": row.get("occurrence_evidence_a"),
                    "compound_b_occurrence_evidence": row.get("occurrence_evidence_b"),
                    "compound_a_source_confidence": _safe_float(row.get("source_confidence_a")),
                    "compound_b_source_confidence": _safe_float(row.get("source_confidence_b")),
                    "shared_source_confidence": _safe_float(row.get("shared_source_confidence")),
                }
                shared_records.append(record)
                evidence_rows.append({
                    "pair_key": key,
                    "compound_a": a,
                    "compound_b": b,
                    **record,
                    "evidence_class": "fooddb_pair_cooccurrence_context",
                    "source_resource": "FoodDB-derived food chemistry bundle",
                    "mapping_caveat": FOOD_SOURCE_CAVEAT,
                })
        shared_quantified = sum(
            1 for r in shared_records
            if r.get("compound_a_occurrence_evidence") == "quantified_occurrence"
            and r.get("compound_b_occurrence_evidence") == "quantified_occurrence"
        )
        shared_confidence = max([r.get("shared_source_confidence") or 0 for r in shared_records], default=0)
        context_rows.append({
            "pair_key": key,
            "compound_a": a,
            "compound_b": b,
            "shared_food_count": int(len(shared)),
            "shared_quantified_food_count": int(shared_quantified),
            "shared_source_confidence": round(float(shared_confidence), 3),
            "shared_foods_json": _json(shared_records),
            "compound_a_sources_json": _json(_top_source_records(a_src, 5)),
            "compound_b_sources_json": _json(_top_source_records(b_src, 5)),
            "source_context_status": "shared_sources_found" if len(shared) else "individual_sources_only" if (not a_src.empty or not b_src.empty) else "no_fooddb_source_match",
            "evidence_class": "fooddb_pair_source_context",
            "source_resource": "FoodDB-derived food chemistry bundle",
            "mapping_caveat": FOOD_SOURCE_CAVEAT,
        })
    return pd.DataFrame(context_rows, columns=context_columns), pd.DataFrame(evidence_rows, columns=evidence_columns)


def augment_kg_with_food_sources(
    kg_path: str | Path,
    matches: pd.DataFrame,
    sources: pd.DataFrame,
    pair_context: pd.DataFrame,
) -> dict[str, int]:
    """Reconcile FoodDB-derived nodes, edges, and materialized tables with the current mapping.

    The operation is idempotent and removes stale FoodDB extension records from earlier
    mappings or different top-N settings while preserving all non-FoodDB KG content.
    """
    path = Path(kg_path)
    empty = {
        "nodes_added": 0, "nodes_removed": 0,
        "edges_added": 0, "edges_removed": 0,
    }
    if not path.exists():
        return empty

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def node_id(prefix: str, value: Any) -> str:
        text = re.sub(r"\s+", "_", str(value).strip())[:180]
        return f"{prefix}:{text}"

    for row in matches[matches["fooddb_compound_id"].notna()].to_dict("records") if not matches.empty else []:
        pesi = row.get("pesi_compound_name")
        public = row.get("fooddb_public_id")
        if public is None or (isinstance(public, float) and pd.isna(public)) or not str(public).strip():
            public = row.get("fooddb_compound_id")
        nodes.extend([
            {"node_id": node_id("Compound", pesi), "node_type": "Compound", "label": pesi, "source_resource": "PESI compound pool", "evidence_class": "real_compound_record"},
            {"node_id": node_id("FoodDBCompound", public), "node_type": "FoodDBCompound", "label": row.get("fooddb_compound_name"), "source_resource": "FoodDB-derived food chemistry bundle", "evidence_class": row.get("evidence_class")},
        ])
        edges.append({
            "src": node_id("Compound", pesi), "dst": node_id("FoodDBCompound", public),
            "rel": "normalized_to_fooddb_compound", "source_resource": "FoodDB-derived food chemistry bundle",
            "evidence_class": row.get("evidence_class"),
        })
    for row in sources.to_dict("records") if not sources.empty else []:
        public = row.get("fooddb_public_id")
        if public is None or (isinstance(public, float) and pd.isna(public)) or not str(public).strip():
            public = row.get("fooddb_compound_id")
        food = row.get("food_public_id")
        if food is None or (isinstance(food, float) and pd.isna(food)) or not str(food).strip():
            food = row.get("food_id")
        nodes.append({
            "node_id": node_id("FoodSource", food), "node_type": "FoodSource", "label": row.get("food_name"),
            "source_resource": "FoodDB-derived food chemistry bundle", "evidence_class": row.get("evidence_class"),
        })
        edges.append({
            "src": node_id("FoodDBCompound", public), "dst": node_id("FoodSource", food),
            "rel": "reported_in_food", "source_resource": "FoodDB-derived food chemistry bundle",
            "evidence_class": row.get("evidence_class"),
        })

    candidate_nodes = pd.DataFrame(nodes).drop_duplicates("node_id", keep="last") if nodes else pd.DataFrame()
    candidate_edges = pd.DataFrame(edges).drop_duplicates(["src", "dst", "rel"], keep="last") if edges else pd.DataFrame()
    extension_node_types = {"FoodDBCompound", "FoodSource"}
    extension_relations = {"normalized_to_fooddb_compound", "reported_in_food"}

    with sqlite3.connect(path) as con:
        matches.to_sql("fooddb_compound_matches", con, if_exists="replace", index=False)
        sources.to_sql("fooddb_food_sources", con, if_exists="replace", index=False)
        pair_context.to_sql("fooddb_pair_source_context", con, if_exists="replace", index=False)

        current_nodes = pd.read_sql_query("SELECT * FROM kg_nodes", con)
        current_edges = pd.read_sql_query("SELECT * FROM kg_edges", con)
        current_node_ids = set(current_nodes.get("node_id", pd.Series(dtype=str)).astype(str))
        current_extension_nodes = current_nodes[current_nodes.get("node_type", pd.Series(index=current_nodes.index, dtype=str)).isin(extension_node_types)]
        old_extension_node_ids = set(current_extension_nodes.get("node_id", pd.Series(dtype=str)).astype(str))

        extension_candidates = (
            candidate_nodes[candidate_nodes["node_type"].isin(extension_node_types)].copy()
            if not candidate_nodes.empty else pd.DataFrame(columns=current_nodes.columns)
        )
        compound_candidates = (
            candidate_nodes[candidate_nodes["node_type"].eq("Compound")].copy()
            if not candidate_nodes.empty else pd.DataFrame(columns=current_nodes.columns)
        )
        missing_compounds = compound_candidates[~compound_candidates["node_id"].astype(str).isin(current_node_ids)] if not compound_candidates.empty else compound_candidates
        new_extension_node_ids = set(extension_candidates.get("node_id", pd.Series(dtype=str)).astype(str))

        core_nodes = current_nodes[~current_nodes.get("node_type", pd.Series(index=current_nodes.index, dtype=str)).isin(extension_node_types)]
        all_nodes = pd.concat([core_nodes, missing_compounds, extension_candidates], ignore_index=True, sort=False)
        all_nodes = all_nodes.drop_duplicates("node_id", keep="first")
        all_nodes.to_sql("kg_nodes", con, if_exists="replace", index=False)

        edge_key = ["src", "dst", "rel"]
        current_extension_edges = current_edges[current_edges.get("rel", pd.Series(index=current_edges.index, dtype=str)).isin(extension_relations)]
        old_extension_keys = set(map(tuple, current_extension_edges.reindex(columns=edge_key).astype(str).itertuples(index=False, name=None)))
        new_extension_keys = set(map(tuple, candidate_edges.reindex(columns=edge_key).astype(str).itertuples(index=False, name=None))) if not candidate_edges.empty else set()
        core_edges = current_edges[~current_edges.get("rel", pd.Series(index=current_edges.index, dtype=str)).isin(extension_relations)]
        all_edges = pd.concat([core_edges, candidate_edges], ignore_index=True, sort=False)
        all_edges = all_edges.drop_duplicates(edge_key, keep="last")
        all_edges.to_sql("kg_edges", con, if_exists="replace", index=False)

    return {
        "nodes_added": len((new_extension_node_ids | set(missing_compounds.get("node_id", pd.Series(dtype=str)).astype(str))) - current_node_ids),
        "nodes_removed": len(old_extension_node_ids - new_extension_node_ids),
        "edges_added": len(new_extension_keys - old_extension_keys),
        "edges_removed": len(old_extension_keys - new_extension_keys),
    }


def refresh_kg_report_with_food_sources(out_dir: str | Path, artifact_dir: str | Path) -> dict[str, Any]:
    """Refresh KG counts after FoodDB nodes/edges are merged into the existing SQLite KG."""
    out = Path(out_dir)
    db_path = Path(artifact_dir) / "pesi_kg.sqlite"
    report_path = out / "aim1_kg_report.json"
    if not db_path.exists():
        return {"status": "kg_missing"}
    existing: dict[str, Any] = {}
    if report_path.exists():
        try:
            existing = json.loads(report_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}
    with sqlite3.connect(db_path) as con:
        node_count = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM kg_nodes", con)["n"].iloc[0])
        edge_count = int(pd.read_sql_query("SELECT COUNT(*) AS n FROM kg_edges", con)["n"].iloc[0])
        node_types = pd.read_sql_query("SELECT node_type, COUNT(*) AS n FROM kg_nodes GROUP BY node_type ORDER BY n DESC", con)
        rels = pd.read_sql_query("SELECT rel, COUNT(*) AS n FROM kg_edges GROUP BY rel ORDER BY n DESC LIMIT 25", con)
        table_counts: dict[str, int] = {}
        for table in ["fooddb_compound_matches", "fooddb_food_sources", "fooddb_pair_source_context"]:
            try:
                table_counts[table] = int(pd.read_sql_query(f'SELECT COUNT(*) AS n FROM "{table}"', con)["n"].iloc[0])
            except Exception:
                table_counts[table] = 0
    existing.update({
        "db_path": str(db_path),
        "node_count": node_count,
        "edge_count": edge_count,
        "node_type_counts": dict(zip(node_types["node_type"].astype(str), node_types["n"].astype(int))),
        "edge_relation_counts_top25": dict(zip(rels["rel"].astype(str), rels["n"].astype(int))),
    })
    source_counts = dict(existing.get("source_table_counts") or {})
    source_counts.update(table_counts)
    existing["source_table_counts"] = source_counts
    existing["food_source_extension"] = {
        "status": "integrated",
        "compound_match_table": "fooddb_compound_matches",
        "food_occurrence_table": "fooddb_food_sources",
        "pair_source_table": "fooddb_pair_source_context",
        "scientific_boundary": FOOD_SOURCE_CAVEAT,
    }
    write_json(report_path, existing)
    return {"status": "refreshed", "node_count": node_count, "edge_count": edge_count, "table_counts": table_counts}


def build_food_source_artifacts(
    raw_dir: str | Path,
    out_dir: str | Path,
    optimized: pd.DataFrame | None = None,
    compound_pool: pd.DataFrame | None = None,
    artifact_dir: str | Path | None = None,
    top_n_per_compound: int = 30,
) -> dict[str, Any]:
    out = ensure_dir(out_dir)
    mapper = FoodDBMapper(raw_dir)
    inventory = mapper.inventory()
    if compound_pool is None:
        pool_path = out / "compound_pool.csv"
        compound_pool = pd.read_csv(pool_path) if pool_path.exists() else pd.DataFrame()
    if optimized is None:
        opt_path = out / "aim4_optimized_interventions.csv"
        optimized = pd.read_csv(opt_path) if opt_path.exists() else pd.DataFrame()

    matches = mapper.match_compounds(compound_pool)
    sources = mapper.food_sources(matches, top_n_per_compound=top_n_per_compound)
    pair_context, pair_evidence = build_pair_source_context(optimized, sources)

    matches.to_csv(out / "compound_fooddb_matches.csv", index=False)
    sources.to_csv(out / "compound_food_sources.csv", index=False)
    pair_context.to_csv(out / "pair_food_source_context.csv", index=False)
    pair_evidence.to_csv(out / "pair_food_source_evidence.csv", index=False)

    matched = int(matches["fooddb_compound_id"].notna().sum()) if not matches.empty else 0
    total = int(len(matches))
    recommended_compounds = sorted(set(optimized.get("compound_a", pd.Series(dtype=str)).dropna().astype(str)) | set(optimized.get("compound_b", pd.Series(dtype=str)).dropna().astype(str))) if optimized is not None and not optimized.empty else []
    matched_names = set(matches.loc[matches["fooddb_compound_id"].notna(), "pesi_compound_name"].astype(str)) if not matches.empty else set()
    recommended_matched = len(set(recommended_compounds) & matched_names)
    kg_update = {"nodes_added": 0, "edges_added": 0}
    kg_report_refresh: dict[str, Any] = {"status": "not_requested"}
    if artifact_dir:
        kg_update = augment_kg_with_food_sources(Path(artifact_dir) / "pesi_kg.sqlite", matches, sources, pair_context)
        kg_report_refresh = refresh_kg_report_with_food_sources(out, artifact_dir)
    report = {
        "status": "completed" if inventory.get("status") == "available" else "food_chemistry_missing",
        "food_chemistry_inventory": inventory,
        "compound_pool_rows": total,
        "matched_compound_rows": matched,
        "compound_match_coverage": round(matched / total, 4) if total else 0.0,
        "recommended_unique_compounds": len(recommended_compounds),
        "recommended_compounds_matched": recommended_matched,
        "recommended_match_coverage": round(recommended_matched / len(recommended_compounds), 4) if recommended_compounds else 0.0,
        "food_source_rows": int(len(sources)),
        "pair_context_rows": int(len(pair_context)),
        "pairs_with_shared_sources": int(pair_context["shared_food_count"].gt(0).sum()) if not pair_context.empty else 0,
        "kg_augmentation": kg_update,
        "kg_report_refresh": kg_report_refresh,
        "matching_policy": [
            "exact InChIKey",
            "unique InChIKey connectivity block",
            "exact normalized FoodDB primary name",
            "exact normalized FoodDB synonym",
        ],
        "evidence_policy": "No food-source claim is emitted without a FoodDB compound match and a FoodDB occurrence record.",
        "caveat": FOOD_SOURCE_CAVEAT,
        "outputs": [
            "compound_fooddb_matches.csv",
            "compound_food_sources.csv",
            "pair_food_source_context.csv",
            "pair_food_source_evidence.csv",
        ],
    }
    write_json(out / "food_source_mapping_report.json", report)
    return report
