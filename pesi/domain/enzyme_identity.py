from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import pandas as pd


ENZYME_IDENTITY_REGISTRY_VERSION = "2026.07.17-v1"
IDENTITY_RESOLUTION_POLICY = "exact identifier or exact curated alias; no broad substring matching"


@dataclass(frozen=True)
class EnzymeIdentityRecord:
    """Curated canonical identity used for conservative target resolution.

    The registry deliberately distinguishes an exact enzyme identity from a
    protein family, a functional activity label, and a non-enzyme target. A
    name is mapped only through exact normalized aliases; broad substring
    matching is intentionally prohibited because it creates biologically false
    family and herbicide-target associations.
    """

    canonical_id: str
    canonical_name: str
    canonical_family: str
    aliases: tuple[str, ...]
    family_aliases: tuple[str, ...] = ()
    entity_type: str = "enzyme"
    resolution_level: str = "exact_enzyme"
    external_ids: tuple[str, ...] = ()
    herbicide_target_family: str | None = None
    notes: str = ""


# Scope-relevant registry. It is intentionally small and auditable rather than
# pretending to be a replacement for UniProt/Rhea/EC/CAZy. Unknown records stay
# unresolved until an identifier-backed mapping is available.
ENZYME_IDENTITY_REGISTRY: tuple[EnzymeIdentityRecord, ...] = (
    EnzymeIdentityRecord(
        canonical_id="EC:2.5.1.19",
        canonical_name="EPSP synthase",
        canonical_family="EPSPS",
        aliases=(
            "5-enolpyruvylshikimate-3-phosphate synthase",
            "5 enolpyruvylshikimate 3 phosphate synthase",
            "EPSP synthase",
            "EPSPS",
        ),
        family_aliases=("EPSPS",),
        external_ids=("EC:2.5.1.19",),
        herbicide_target_family="EPSPS",
    ),
    EnzymeIdentityRecord(
        canonical_id="EC:2.2.1.6",
        canonical_name="acetolactate synthase",
        canonical_family="ALS/AHAS",
        aliases=(
            "acetolactate synthase",
            "acetohydroxyacid synthase",
            "ALS",
            "AHAS",
            "ALS/AHAS",
        ),
        family_aliases=("ALS", "AHAS", "ALS/AHAS"),
        external_ids=("EC:2.2.1.6",),
        herbicide_target_family="ALS/AHAS",
    ),
    EnzymeIdentityRecord(
        canonical_id="EC:6.4.1.2",
        canonical_name="acetyl-CoA carboxylase",
        canonical_family="ACCase",
        aliases=("acetyl-CoA carboxylase", "acetyl coa carboxylase", "ACCase"),
        family_aliases=("ACCase",),
        external_ids=("EC:6.4.1.2",),
        herbicide_target_family="ACCase",
    ),
    EnzymeIdentityRecord(
        canonical_id="EC:1.3.3.4",
        canonical_name="protoporphyrinogen oxidase",
        canonical_family="PPO",
        aliases=("protoporphyrinogen oxidase", "PPO", "Protox"),
        family_aliases=("PPO", "Protox"),
        external_ids=("EC:1.3.3.4",),
        herbicide_target_family="PPO",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:PSII_TARGET",
        canonical_name="photosystem II electron-transport target",
        canonical_family="PSII",
        aliases=("photosystem II", "PSII", "photosystem ii electron transport"),
        family_aliases=("PSII",),
        entity_type="non_enzyme_target",
        resolution_level="exact_target",
        herbicide_target_family="PSII",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:HCT",
        canonical_name="shikimate O-hydroxycinnamoyltransferase",
        canonical_family="BAHD acyltransferase",
        aliases=(
            "shikimate O-hydroxycinnamoyltransferase",
            "hydroxycinnamoyl-coenzyme A:shikimate/quinate hydroxycinnamoyl transferase",
            "hydroxycinnamoyl-coa:shikimate/quinate hydroxycinnamoyl transferase",
            "hydroxycinnamoyl-coa:shikimate hydroxycinnamoyl transferase 1",
            "hydroxycinnamate-CoA shikimate transferase",
            "HCT",
        ),
        family_aliases=("BAHD acyltransferase", "plant acyltransferase family"),
        notes="Canonicalizes HCT naming variants without equating HCT with EPSPS.",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:CSE",
        canonical_name="caffeoyl shikimate esterase",
        canonical_family="caffeoyl shikimate esterase",
        aliases=("caffeoyl shikimate esterase", "caffeoylshikimate esterase", "CSE"),
        family_aliases=("caffeoyl shikimate esterase", "esterase", "hydrolase"),
        external_ids=("UniProtKB:Q9C942",),
        notes="Hydrolytic esterase identity; not a BAHD acyltransferase.",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:GH3_ACYL_ACID_AMIDO_SYNTHETASE",
        canonical_name="GH3 acyl acid amido synthetase",
        canonical_family="GH3 acyl acid amido synthetase",
        aliases=(
            "GH3 acyl adenylase-family enzyme",
            "GH3 acyl adenylase family enzyme",
            "GH3 acyl acid amido synthetase",
        ),
        family_aliases=("GH3 acyl acid amido synthetase", "GH3"),
        notes="Plant GH3 acyl-activating synthetases are distinct from BAHD acyltransferases and CAZy GH3.",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:GH3_ISOCHORISMOYL_GLUTAMATE_SYNTHASE",
        canonical_name="isochorismoyl-glutamate synthase",
        canonical_family="GH3 acyl acid amido synthetase",
        aliases=(
            "isochorismoyl-glutamate synthase",
            "isochorismoyl glutamate synthase",
            "Isochorismoyl-Glutamate Synthase; GH3 acyl adenylase-family enzyme",
        ),
        family_aliases=("GH3 acyl acid amido synthetase", "GH3"),
        notes="Specific GH3-family acyl acid amido synthetase identity.",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:DROUGHT_BCAT",
        canonical_name="drought-induced branched-chain amino-acid aminotransferase",
        canonical_family="branched-chain amino-acid aminotransferase",
        aliases=(
            "Drought-Induced Branched-Chain Amino Acid Aminotransferase",
            "drought induced branched chain amino acid aminotransferase",
        ),
        family_aliases=("Aminotransferase", "branched-chain amino-acid aminotransferase", "BCAT"),
    ),
    EnzymeIdentityRecord(
        canonical_id="EC:3.2.1.1",
        canonical_name="alpha-amylase",
        canonical_family="alpha-amylase",
        aliases=("alpha-amylase", "alpha amylase", "α-amylase"),
        family_aliases=("amylase", "alpha-amylase"),
        external_ids=("EC:3.2.1.1",),
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:ACTIVITY_CELLULASE",
        canonical_name="cellulase activity",
        canonical_family="cellulose-active carbohydrate enzyme",
        aliases=("cellulase", "cellulase activity"),
        family_aliases=("CAZy", "glycoside hydrolase", "cellulose-active carbohydrate enzyme"),
        entity_type="functional_activity",
        resolution_level="functional_category",
        notes="Broad activity label; not an exact protein or CAZy family identity.",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:CYTOCHROME_P450_FAMILY",
        canonical_name="cytochrome P450 family",
        canonical_family="cytochrome P450",
        aliases=("cytochrome P450", "P450", "CYP450"),
        family_aliases=("Cytochrome P450", "P450", "CYP"),
        entity_type="enzyme_family",
        resolution_level="family",
    ),
    EnzymeIdentityRecord(
        canonical_id="PESI:PEROXIDASE_FAMILY",
        canonical_name="peroxidase family",
        canonical_family="peroxidase",
        aliases=("peroxidase",),
        family_aliases=("Peroxidase",),
        entity_type="enzyme_family",
        resolution_level="family",
    ),
)


def normalize_identity_text(value: Any) -> str:
    text = str(value or "").casefold()
    text = text.replace("α", "alpha").replace("β", "beta").replace("γ", "gamma")
    text = text.replace("coenzyme a", "coa")
    text = re.sub(r"\bco\s*a\b", "coa", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()




def normalize_external_id(value: Any, *, namespace: str | None = None) -> str:
    text = str(value or "").strip()
    if not text or text.casefold() in {"nan", "none", "null"}:
        return ""
    compact = re.sub(r"\s+", "", text).upper()
    ns = (namespace or "").upper()
    if ns == "EC" or re.fullmatch(r"(?:EC:?)?[1-7](?:\.[0-9-]+){1,3}", compact):
        compact = re.sub(r"^EC:?", "", compact)
        return f"EC:{compact}"
    if ns in {"UNIPROT", "UNIPROTKB"} or compact.startswith("UNIPROT"):
        compact = re.sub(r"^UNIPROTKB?:?", "", compact)
        return f"UNIPROTKB:{compact}"
    if ns == "RHEA" or compact.startswith("RHEA"):
        compact = re.sub(r"^RHEA:?", "", compact)
        return f"RHEA:{compact}"
    return compact

def _stable_unresolved_id(name: Any) -> str:
    normalized = normalize_identity_text(name) or "unresolved"
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"PESI:UNRESOLVED:{digest}"


def _split_candidate_names(name: Any) -> list[str]:
    raw = str(name or "").strip()
    if not raw:
        return []
    parts = [raw]
    parts.extend(x.strip() for x in re.split(r"[;|]", raw) if x.strip())
    output: list[str] = []
    seen: set[str] = set()
    for part in parts:
        norm = normalize_identity_text(part)
        if norm and norm not in seen:
            seen.add(norm)
            output.append(part)
    return output


def _registry_alias_index() -> dict[str, list[EnzymeIdentityRecord]]:
    index: dict[str, list[EnzymeIdentityRecord]] = {}
    for record in ENZYME_IDENTITY_REGISTRY:
        for alias in (record.canonical_name, *record.aliases):
            index.setdefault(normalize_identity_text(alias), []).append(record)
    return index


_ALIAS_INDEX = _registry_alias_index()


def _registry_external_id_index() -> dict[str, list[EnzymeIdentityRecord]]:
    index: dict[str, list[EnzymeIdentityRecord]] = {}
    for record in ENZYME_IDENTITY_REGISTRY:
        for external_id in record.external_ids:
            normalized = normalize_external_id(external_id)
            if normalized:
                index.setdefault(normalized, []).append(record)
    return index


_EXTERNAL_ID_INDEX = _registry_external_id_index()


def _family_validation(record: EnzymeIdentityRecord, reported_family: Any) -> dict[str, Any]:
    reported = str(reported_family or "").strip()
    reported_norm = normalize_identity_text(reported)
    expected_norms = {
        normalize_identity_text(record.canonical_family),
        *(normalize_identity_text(alias) for alias in record.family_aliases),
    }
    expected_norms.discard("")

    if not reported_norm:
        return {
            "family_validation_status": "missing",
            "family_validation_confidence": 0.0,
            "family_reported": None,
            "family_canonical": record.canonical_family,
            "family_correction_applied": False,
            "family_validation_reason": "No reported family was available; the registry family is retained as curated metadata.",
        }
    if record.canonical_id.startswith("CAZY:") and reported_norm in {"gh", "gt", "ce", "pl", "aa", "cbm", "glycoside hydrolase", "cazy"}:
        status = "refined"
        reason = "A broad CAZy class label was refined to the identifier-specific CAZy family or subfamily."
        confidence = 0.95
        correction = True
    elif record.resolution_level == "functional_category" and reported_norm in {"cazy", "glycoside hydrolase", "cellulase"}:
        status = "compatible_broad"
        reason = "Reported family is compatible with the broad activity label but does not establish an exact enzyme family."
        confidence = 0.70
        correction = True
    elif reported_norm in expected_norms:
        status = "validated"
        reason = "Reported family matches the canonical family or a curated family alias."
        confidence = 1.0
        correction = reported_norm != normalize_identity_text(record.canonical_family)
    else:
        status = "conflict_corrected"
        reason = (
            f"Reported family '{reported}' conflicts with the curated identity family "
            f"'{record.canonical_family}' and was not used for canonical grouping."
        )
        confidence = 0.98
        correction = True

    return {
        "family_validation_status": status,
        "family_validation_confidence": confidence,
        "family_reported": reported,
        "family_canonical": record.canonical_family,
        "family_correction_applied": correction,
        "family_validation_reason": reason,
    }


def _dynamic_cazy_identity(name: Any, family: Any) -> EnzymeIdentityRecord | None:
    raw = str(name or "").strip().upper().replace("-", "_")
    match = re.fullmatch(r"(GH|GT|CE|PL|AA|CBM)\s*([0-9]+(?:_[0-9]+)?)", raw)
    if not match:
        # Accept canonical display labels emitted by this resolver so repeated
        # API/report passes remain idempotent.
        subfamily_match = re.fullmatch(
            r"(?:GH|GT|CE|PL|AA|CBM)[0-9]+\s+SUBFAMILY\s+(GH|GT|CE|PL|AA|CBM)([0-9]+_[0-9]+)",
            raw,
        )
        if subfamily_match:
            match = subfamily_match
        else:
            class_names = {
                "GLYCOSIDE HYDROLASE FAMILY": "GH",
                "GLYCOSYLTRANSFERASE FAMILY": "GT",
                "CARBOHYDRATE ESTERASE FAMILY": "CE",
                "POLYSACCHARIDE LYASE FAMILY": "PL",
                "AUXILIARY ACTIVITY FAMILY": "AA",
                "CARBOHYDRATE_BINDING MODULE FAMILY": "CBM",
                "CARBOHYDRATE BINDING MODULE FAMILY": "CBM",
            }
            for prefix, cazy_class_name in class_names.items():
                canonical_match = re.fullmatch(re.escape(prefix) + r"\s+([0-9]+)", raw)
                if canonical_match:
                    match = (cazy_class_name, canonical_match.group(1))
                    break
    if not match:
        return None
    if isinstance(match, tuple):
        cazy_class, number = match
    else:
        cazy_class, number = match.groups()
    family_id = f"{cazy_class}{number}"
    if "_" in number:
        base_family = f"{cazy_class}{number.split('_', 1)[0]}"
        canonical_name = f"{base_family} subfamily {family_id}"
        canonical_family = base_family
        level = "subfamily"
    else:
        canonical_name = {
            "GH": "glycoside hydrolase family",
            "GT": "glycosyltransferase family",
            "CE": "carbohydrate esterase family",
            "PL": "polysaccharide lyase family",
            "AA": "auxiliary activity family",
            "CBM": "carbohydrate-binding module family",
        }.get(cazy_class, "CAZy family") + f" {number}"
        canonical_family = family_id
        level = "family"
    return EnzymeIdentityRecord(
        canonical_id=f"CAZY:{family_id}",
        canonical_name=canonical_name,
        canonical_family=canonical_family,
        aliases=(raw, family_id),
        family_aliases=(cazy_class, "CAZy", canonical_family),
        entity_type="enzyme_family",
        resolution_level=level,
        external_ids=(f"CAZY:{family_id}",),
    )


def _dynamic_ec_identity(name: Any, family: Any) -> EnzymeIdentityRecord | None:
    text = str(name or "").strip()
    match = re.fullmatch(r"(?:EC\s*)?([1-7](?:\.[0-9-]+){1,3})", text, flags=re.IGNORECASE)
    if not match:
        return None
    ec = match.group(1)
    return EnzymeIdentityRecord(
        canonical_id=f"EC:{ec}",
        canonical_name=f"EC {ec}",
        canonical_family=f"EC class {ec.split('.', 1)[0]}",
        aliases=(text,),
        family_aliases=(str(family or ""),),
        entity_type="enzyme_classification",
        resolution_level="identifier_only",
        external_ids=(f"EC:{ec}",),
        notes="Identifier is resolved, but a specific common enzyme name was not available.",
    )




def _source_dataset_family_validation(record: EnzymeIdentityRecord | None, source: Any) -> dict[str, Any]:
    """Track whether the source container's advertised family matches the canonical identity.

    A spreadsheet or source collection can contain misfiled records. The source
    container is therefore provenance, not proof of family membership.
    """

    raw = str(source or "").strip()
    norm = normalize_identity_text(raw)
    hints: list[tuple[str, str]] = [
        ("bahd", "BAHD acyltransferase"),
        ("aminotransferase", "aminotransferase"),
        ("cazy", "CAZy"),
        ("cytochrome p450", "cytochrome P450"),
        ("p450", "cytochrome P450"),
        ("peroxidase", "peroxidase"),
        ("methyltransferase", "methyltransferase"),
        ("dioxygenase", "dioxygenase"),
        ("gdsl", "GDSL lipase/esterase"),
    ]
    hint = next((label for token, label in hints if token in norm), None)
    if not raw or not hint:
        return {
            "source_dataset_family_hint": hint,
            "source_dataset_family_validation_status": "not_assessed",
            "source_dataset_family_conflict": False,
            "source_dataset_family_reason": "No family-bearing source-container label was available for validation.",
        }
    if record is None:
        return {
            "source_dataset_family_hint": hint,
            "source_dataset_family_validation_status": "unresolved_identity",
            "source_dataset_family_conflict": False,
            "source_dataset_family_reason": "The source container has a family label, but the enzyme identity is unresolved.",
        }

    family_norm = normalize_identity_text(record.canonical_family)
    canonical_id = str(record.canonical_id)
    compatibility = {
        "BAHD acyltransferase": "bahd" in family_norm,
        "aminotransferase": "aminotransferase" in family_norm,
        "CAZy": canonical_id.startswith("CAZY:") or any(token in family_norm for token in ("glycoside hydrolase", "cazy", "cellulose active carbohydrate")),
        "cytochrome P450": "p450" in family_norm,
        "peroxidase": "peroxidase" in family_norm,
        "methyltransferase": "methyltransferase" in family_norm,
        "dioxygenase": "dioxygenase" in family_norm,
        "GDSL lipase/esterase": "gdsl" in family_norm or "lipase" in family_norm or "esterase" in family_norm,
    }.get(hint, False)
    if compatibility:
        return {
            "source_dataset_family_hint": hint,
            "source_dataset_family_validation_status": "aligned",
            "source_dataset_family_conflict": False,
            "source_dataset_family_reason": f"Source-container family label '{hint}' is compatible with the canonical family.",
        }
    return {
        "source_dataset_family_hint": hint,
        "source_dataset_family_validation_status": "conflict",
        "source_dataset_family_conflict": True,
        "source_dataset_family_reason": (
            f"Source container '{raw}' advertises family '{hint}', but the canonical identity belongs to "
            f"'{record.canonical_family}'. The row is retained for provenance and down-weighted as a source-family conflict."
        ),
    }

def resolve_enzyme_identity(
    enzyme_name: Any,
    enzyme_family: Any = "",
    *,
    source: Any = None,
    ec_number: Any = None,
    uniprot_id: Any = None,
    rhea_id: Any = None,
) -> dict[str, Any]:
    """Resolve an enzyme conservatively and expose all uncertainty.

    Exact normalized aliases, explicit EC identifiers, and CAZy identifiers are
    accepted. Partial substring matches are not accepted. The function never
    silently upgrades a broad activity name (for example ``cellulase``) into an
    exact protein identity.
    """

    candidates = _split_candidate_names(enzyme_name)
    matches: list[tuple[EnzymeIdentityRecord, str, str]] = []
    for candidate in candidates:
        normalized = normalize_identity_text(candidate)
        for record in _ALIAS_INDEX.get(normalized, []):
            basis = "exact_canonical_name" if normalized == normalize_identity_text(record.canonical_name) else "exact_curated_alias"
            matches.append((record, candidate, basis))

    identifier_candidates = [
        normalize_external_id(ec_number, namespace="EC"),
        normalize_external_id(uniprot_id, namespace="UNIPROTKB"),
        normalize_external_id(rhea_id, namespace="RHEA"),
        normalize_external_id(enzyme_name),
    ]
    identifier_matches: list[tuple[EnzymeIdentityRecord, str, str]] = []
    for identifier in identifier_candidates:
        if not identifier:
            continue
        for record in _EXTERNAL_ID_INDEX.get(identifier, []):
            identifier_matches.append((record, identifier, "explicit_curated_identifier"))

    # Identifier-backed mappings take precedence over names. A conflicting name
    # is retained as an explicit warning rather than silently overriding the ID.
    name_match_ids = {item[0].canonical_id for item in matches}
    identifier_match_ids = {item[0].canonical_id for item in identifier_matches}
    identifier_name_conflict = bool(identifier_match_ids and name_match_ids and identifier_match_ids != name_match_ids)
    if identifier_matches:
        matches = identifier_matches + matches

    # Prefer identifier-backed and then the most specific identity when a composite
    # name contains both a specific enzyme and a broader family description.
    if matches:
        level_rank = {
            "exact_enzyme": 6,
            "exact_target": 6,
            "identifier_only": 5,
            "subfamily": 4,
            "family": 3,
            "functional_category": 2,
        }
        matches.sort(
            key=lambda item: (
                1 if item[2] == "explicit_curated_identifier" else 0,
                level_rank.get(item[0].resolution_level, 0),
                len(normalize_identity_text(item[1])),
            ),
            reverse=True,
        )
        record, matched_alias, basis = matches[0]
        ambiguity = sorted({item[0].canonical_id for item in matches})
        ambiguous = len(ambiguity) > 1 and matches[0][0].canonical_id != matches[1][0].canonical_id
    else:
        record = None
        matched_alias = ""
        basis = ""
        ambiguous = False
        ambiguity = []

    if record is None and ec_number:
        record = _dynamic_ec_identity(normalize_external_id(ec_number, namespace="EC").removeprefix("EC:"), enzyme_family)
        matched_alias = str(ec_number)
        basis = "explicit_ec_identifier"
    if record is None:
        record = _dynamic_cazy_identity(enzyme_name, enzyme_family)
        if record:
            matched_alias = str(enzyme_name)
            basis = "explicit_cazy_identifier"
    if record is None:
        record = _dynamic_ec_identity(enzyme_name, enzyme_family)
        if record:
            matched_alias = str(enzyme_name)
            basis = "explicit_ec_identifier"

    if record is None:
        canonical_id = _stable_unresolved_id(enzyme_name)
        normalized_name = str(enzyme_name or "Unresolved enzyme").strip() or "Unresolved enzyme"
        return {
            "canonical_id": canonical_id,
            "canonical_name": normalized_name,
            "canonical_family": str(enzyme_family or "unresolved").strip() or "unresolved",
            "identity_registry_version": ENZYME_IDENTITY_REGISTRY_VERSION,
            "identity_resolution_policy": IDENTITY_RESOLUTION_POLICY,
            "canonical_id_namespace": "PESI",
            "external_identifier_backed": False,
            "entity_type": "unresolved",
            "identity_resolution_status": "unresolved",
            "identity_resolution_level": "unresolved",
            "identity_match_basis": "no_exact_alias_or_identifier_match",
            "identity_match_confidence": 0.0,
            "identity_matched_alias": None,
            "identity_ambiguity": [],
            "identity_warning": "No identifier-backed or exact curated alias mapping was available.",
            "external_ids": [
                x for x in (
                    normalize_external_id(ec_number, namespace="EC"),
                    normalize_external_id(uniprot_id, namespace="UNIPROTKB"),
                    normalize_external_id(rhea_id, namespace="RHEA"),
                ) if x
            ],
            "herbicide_target_family": None,
            "source": source,
            "reported_name": enzyme_name,
            **_source_dataset_family_validation(None, source),
            **{
                "family_validation_status": "unresolved",
                "family_validation_confidence": 0.0,
                "family_reported": str(enzyme_family or "").strip() or None,
                "family_canonical": str(enzyme_family or "unresolved").strip() or "unresolved",
                "family_correction_applied": False,
                "family_validation_reason": "Family could not be validated because the enzyme identity is unresolved.",
            },
        }

    family = _family_validation(record, enzyme_family)
    confidence_by_level = {
        "exact_enzyme": 1.0,
        "exact_target": 1.0,
        "identifier_only": 0.95,
        "subfamily": 0.95,
        "family": 0.90,
        "functional_category": 0.65,
    }
    confidence = confidence_by_level.get(record.resolution_level, 0.80)
    if basis == "exact_curated_alias":
        confidence = min(confidence, 0.98)
    if ambiguous:
        confidence = min(confidence, 0.70)

    warning_parts: list[str] = []
    if record.resolution_level == "functional_category":
        warning_parts.append("Broad functional activity; not an exact protein or enzyme-family identity.")
    if ambiguous:
        warning_parts.append("Composite name matched more than one registry identity; the most specific exact alias was selected.")
    if identifier_name_conflict:
        warning_parts.append("The explicit identifier conflicts with the reported enzyme name; the identifier-backed identity was retained.")
    if family["family_validation_status"] == "conflict_corrected":
        warning_parts.append(family["family_validation_reason"])

    external_ids = [normalize_external_id(value) for value in record.external_ids if normalize_external_id(value)]
    for value, namespace in ((ec_number, "EC"), (uniprot_id, "UNIPROTKB"), (rhea_id, "RHEA")):
        normalized = normalize_external_id(value, namespace=namespace)
        if normalized and normalized not in external_ids:
            external_ids.append(normalized)

    return {
        "canonical_id": record.canonical_id,
        "canonical_name": record.canonical_name,
        "canonical_family": record.canonical_family,
        "identity_registry_version": ENZYME_IDENTITY_REGISTRY_VERSION,
        "identity_resolution_policy": IDENTITY_RESOLUTION_POLICY,
        "canonical_id_namespace": record.canonical_id.split(":", 1)[0],
        "external_identifier_backed": bool(record.external_ids),
        "entity_type": record.entity_type,
        "identity_resolution_status": "resolved_with_warning" if warning_parts else "resolved",
        "identity_resolution_level": record.resolution_level,
        "identity_match_basis": basis,
        "identity_match_confidence": round(confidence, 3),
        "identity_matched_alias": matched_alias,
        "identity_ambiguity": ambiguity if ambiguous else [],
        "identity_warning": " ".join(warning_parts) or None,
        "external_ids": external_ids,
        "herbicide_target_family": record.herbicide_target_family,
        "source": source,
        "reported_name": enzyme_name,
        **_source_dataset_family_validation(record, source),
        **family,
    }


def canonical_target_key(enzyme_name: Any, enzyme_family: Any = "", **kwargs: Any) -> str:
    return str(resolve_enzyme_identity(enzyme_name, enzyme_family, **kwargs)["canonical_id"])


def canonicalize_enzyme_frame(
    frame: pd.DataFrame,
    *,
    name_col: str = "enzyme_name",
    family_col: str = "enzyme_family",
    source_col: str = "source_evidence",
    replace_display_fields: bool = True,
) -> pd.DataFrame:
    """Attach canonical identity fields and optionally replace display fields.

    Original values are always retained in ``enzyme_name_reported`` and
    ``enzyme_family_reported``. Rows are not dropped here; callers can perform
    deterministic de-duplication using ``enzyme_canonical_id`` together with
    stage or scenario keys appropriate to their workflow.
    """

    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    if name_col not in out.columns:
        return out
    if family_col not in out.columns:
        out[family_col] = ""
    if "enzyme_name_reported" not in out.columns:
        out["enzyme_name_reported"] = out[name_col]
    if "enzyme_family_reported" not in out.columns:
        out["enzyme_family_reported"] = out[family_col]

    def resolve_row(row: pd.Series) -> dict[str, Any]:
        return resolve_enzyme_identity(
            row.get(name_col),
            row.get(family_col),
            source=row.get(source_col),
            ec_number=row.get("ec_number"),
            uniprot_id=row.get("uniprot_id") or row.get("entry"),
            rhea_id=row.get("rhea_id"),
        )

    resolved = out.apply(resolve_row, axis=1).apply(pd.Series)
    rename = {
        "canonical_id": "enzyme_canonical_id",
        "canonical_name": "enzyme_name_canonical",
        "canonical_family": "enzyme_family_canonical",
    }
    resolved = resolved.rename(columns=rename)
    for column in resolved.columns:
        out[column] = resolved[column].values
    if replace_display_fields:
        out[name_col] = out["enzyme_name_canonical"]
        out[family_col] = out["enzyme_family_canonical"]
        if "enzyme_key" in out.columns:
            out["enzyme_key"] = out["enzyme_canonical_id"]
    return out


def consolidate_enzyme_records(
    records: Iterable[dict[str, Any]],
    *,
    name_key: str = "target",
    family_key: str = "target_family",
    stage_key: str = "stage",
) -> list[dict[str, Any]]:
    """Consolidate synonymous targets while retaining aliases and provenance."""

    output: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for raw in records:
        row = dict(raw)
        identity = resolve_enzyme_identity(row.get(name_key), row.get(family_key), source=row.get("source"))
        stage = normalize_identity_text(row.get(stage_key))
        key = (str(identity["canonical_id"]), stage)
        if key not in output:
            order.append(key)
            row["target_reported"] = row.get(name_key)
            row[name_key] = identity["canonical_name"]
            row[family_key] = identity["canonical_family"]
            row["enzyme_identity"] = identity
            row["target_aliases"] = [str(identity.get("reported_name") or row.get(name_key))]
            row["consolidated_record_count"] = 1
            output[key] = row
        else:
            existing = output[key]
            alias = str(row.get(name_key) or "").strip()
            if alias and alias.casefold() not in {x.casefold() for x in existing.get("target_aliases", [])}:
                existing.setdefault("target_aliases", []).append(alias)
            existing["consolidated_record_count"] = int(existing.get("consolidated_record_count") or 1) + 1
            # Retain the strongest available evidence score without multiplying
            # synonymous rows.
            for score_key in ("critical_transition_score", "review_fit", "candidate_fit", "pairing_support"):
                try:
                    current = float(existing.get(score_key))
                except (TypeError, ValueError):
                    current = float("-inf")
                try:
                    candidate = float(row.get(score_key))
                except (TypeError, ValueError):
                    candidate = float("-inf")
                if candidate > current:
                    existing[score_key] = row.get(score_key)
    return [output[key] for key in order]


def registry_as_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in ENZYME_IDENTITY_REGISTRY:
        row = asdict(record)
        row["identity_registry_version"] = ENZYME_IDENTITY_REGISTRY_VERSION
        row["identity_resolution_policy"] = IDENTITY_RESOLUTION_POLICY
        row["external_identifier_backed"] = bool(record.external_ids)
        for key, value in list(row.items()):
            if isinstance(value, tuple):
                row[key] = ";".join(value)
        rows.append(row)
    return rows
