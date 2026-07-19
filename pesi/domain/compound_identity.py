from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

import pandas as pd


COMPOUND_IDENTITY_POLICY_VERSION = "2026.07.19-v1"
COMPOUND_IDENTITY_POLICY = (
    "full InChIKey, then canonical isomeric SMILES hash, then curated source identifier, "
    "then normalized-name fallback; pair keys are unordered canonical compound IDs"
)


def _clean(value: Any) -> str:
    if value is None:
        return ""
    try:
        if isinstance(value, float) and pd.isna(value):
            return ""
    except Exception:
        pass
    text = str(value).strip()
    return "" if text.casefold() in {"", "nan", "none", "null"} else text


def normalize_compound_name(value: Any) -> str:
    text = _clean(value).casefold()
    text = text.replace("α", "alpha").replace("β", "beta").replace("γ", "gamma")
    text = re.sub(r"[\u2010-\u2015]", "-", text)
    text = re.sub(r"[^a-z0-9+\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_inchikey(value: Any) -> str:
    text = _clean(value).upper().replace(" ", "")
    return text if re.fullmatch(r"[A-Z]{14}-[A-Z]{10}-[A-Z]", text) else ""


def structure_identifiers(smiles: Any) -> tuple[str | None, str | None]:
    text = _clean(smiles)
    if not text:
        return None, None
    try:
        from rdkit import Chem, RDLogger
        from rdkit.Chem import inchi

        RDLogger.DisableLog("rdApp.*")
        mol = Chem.MolFromSmiles(text)
        if mol is None:
            return None, None
        canonical = Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)
        key = normalize_inchikey(inchi.MolToInchiKey(mol))
        return canonical or None, key or None
    except Exception:
        return None, None


def _digest(namespace: str, value: str, length: int = 24) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]
    return f"{namespace}:{digest}"


def canonical_compound_identity(
    *,
    name: Any,
    smiles: Any = None,
    canonical_smiles: Any = None,
    inchikey: Any = None,
    source_id: Any = None,
    source_resource: Any = None,
) -> dict[str, Any]:
    """Return a stable, auditable compound identity without inventing structure.

    Structure-backed identity is used only when a valid full InChIKey or a
    parseable canonical isomeric SMILES is available. Source identifiers are
    retained as curated record identities. Name hashes are explicitly marked as
    fallbacks and must not be treated as chemical-structure equivalence.
    """

    reported_name = _clean(name) or "Unresolved compound"
    normalized_name = normalize_compound_name(reported_name)
    supplied_key = normalize_inchikey(inchikey)
    supplied_canonical = _clean(canonical_smiles)
    # Never trust a caller-provided SMILES merely because it is named
    # ``canonical_smiles``. Parse and canonicalize it through RDKit before it
    # can establish structure-backed identity.
    derived_canonical, derived_key = structure_identifiers(supplied_canonical or smiles)
    key = supplied_key or normalize_inchikey(derived_key)
    canonical = _clean(derived_canonical)

    if key:
        canonical_id = f"INCHIKEY:{key}"
        level = "full_inchikey"
        status = "resolved"
        basis = "full_inchikey"
        structure_backed = True
        confidence = 1.0
    elif canonical:
        canonical_id = _digest("SMILES_SHA256", canonical)
        level = "canonical_isomeric_smiles"
        status = "resolved"
        basis = "canonical_isomeric_smiles_hash"
        structure_backed = True
        confidence = 0.98
    elif _clean(source_id):
        source = normalize_compound_name(source_resource) or "source"
        canonical_id = _digest("SOURCE_RECORD", f"{source}|{_clean(source_id)}")
        level = "curated_source_record"
        status = "resolved_without_structure"
        basis = "curated_source_identifier"
        structure_backed = False
        confidence = 0.85
    else:
        canonical_id = _digest("NAME_FALLBACK", normalized_name or "unresolved")
        level = "normalized_name_fallback"
        status = "fallback"
        basis = "normalized_name_hash"
        structure_backed = False
        confidence = 0.45 if normalized_name else 0.0

    connectivity = key.split("-", 1)[0] if key else None
    return {
        "canonical_compound_id": canonical_id,
        "canonical_compound_name": reported_name,
        "compound_name_normalized": normalized_name,
        "canonical_smiles": canonical or None,
        "inchikey": key or None,
        "inchikey_connectivity": connectivity,
        "compound_identity_status": status,
        "compound_identity_level": level,
        "compound_identity_basis": basis,
        "compound_identity_confidence": confidence,
        "structure_backed_identity": structure_backed,
        "compound_identity_policy_version": COMPOUND_IDENTITY_POLICY_VERSION,
        "compound_identity_policy": COMPOUND_IDENTITY_POLICY,
        "source_record_id": _clean(source_id) or None,
        "source_resource": _clean(source_resource) or None,
        "reported_name": reported_name,
    }


def identity_from_mapping(value: Mapping[str, Any] | None, *, name: Any = None) -> dict[str, Any]:
    row = dict(value or {})
    return canonical_compound_identity(
        name=name or row.get("compound_name") or row.get("pesi_compound_name") or row.get("name") or row.get("compound_id"),
        smiles=row.get("smiles") or row.get("pesi_smiles"),
        canonical_smiles=row.get("canonical_smiles") or row.get("pesi_canonical_smiles"),
        inchikey=row.get("inchikey") or row.get("pesi_inchikey"),
        source_id=row.get("compound_id") or row.get("source_record_id"),
        source_resource=row.get("source_resource"),
    )


def canonical_compound_key(value: Any, *, fallback_name: Any = None) -> str:
    if isinstance(value, Mapping):
        direct = _clean(value.get("canonical_compound_id") or value.get("pesi_compound_canonical_id"))
        if direct:
            return direct
        return str(identity_from_mapping(value, name=fallback_name).get("canonical_compound_id"))
    text = _clean(value)
    if re.match(r"^(?:INCHIKEY|SMILES_SHA256|SOURCE_RECORD|NAME_FALLBACK):", text):
        return text
    return str(canonical_compound_identity(name=fallback_name or value).get("canonical_compound_id"))


def canonical_compound_pair_ids(
    compound_a: Any,
    compound_b: Any,
    *,
    compound_a_name: Any = None,
    compound_b_name: Any = None,
) -> tuple[str, str]:
    a_id = canonical_compound_key(compound_a, fallback_name=compound_a_name)
    b_id = canonical_compound_key(compound_b, fallback_name=compound_b_name)
    left, right = sorted([a_id, b_id])
    return left, right


def canonical_compound_pair_key(
    compound_a: Any,
    compound_b: Any,
    *,
    compound_a_name: Any = None,
    compound_b_name: Any = None,
) -> str:
    left, right = canonical_compound_pair_ids(
        compound_a,
        compound_b,
        compound_a_name=compound_a_name,
        compound_b_name=compound_b_name,
    )
    return f"{left}||{right}"
