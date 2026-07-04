from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


SOLVENT_OR_VEHICLE_NAMES = {
    "water", "ethanol", "methanol", "propanol", "isopropanol", "acetone", "acetonitrile",
    "dmso", "dimethyl sulfoxide", "dimethylsulfoxide", "hexane", "heptane", "toluene",
    "benzene", "chloroform", "dichloromethane", "ethyl acetate", "glycerol", "propylene glycol",
    "polyethylene glycol", "peg", "butanol", "1-butanol", "2-butanol", "2-ethoxyethanol",
}

BUFFER_OR_SALT_NAMES = {
    "sodium chloride", "potassium chloride", "sodium phosphate", "potassium phosphate",
    "tris", "hepes", "mops", "mes", "pbs", "phosphate buffer", "carbonate", "bicarbonate",
    "ammonium sulfate", "urea", "edta", "magnesium chloride", "calcium chloride",
}

REACTIVE_ALDEHYDE_NAMES = {
    "formaldehyde", "glyoxal", "methylglyoxal", "d-lactoaldehyde", "lactoaldehyde", "acetaldehyde",
    "glutaraldehyde", "malondialdehyde", "benzaldehyde", "4-hydroxynonenal", "hydroxynonenal",
}

COMMON_ASSAY_CHEMICAL_NAMES = {
    "atp", "adp", "amp", "nad", "nadh", "nadp", "nadph", "coa", "acetyl-coa",
    "glucose", "fructose", "sucrose", "ribose", "pyruvate", "oxaloacetate", "malate",
    "citrate", "succinate", "glutamate", "glycine", "alanine", "serine", "tryptophan",
    "phenylalanine", "tyrosine", "l-proline", "proline", "hydrogen peroxide",
}

NATURAL_PRODUCT_KEYWORDS = {
    "flavonoid", "phenolic", "phenol", "tannin", "terpenoid", "terpene", "alkaloid",
    "cyanogenic", "glycoside", "coumarin", "quinone", "saponin", "lactone", "stilbene",
    "lignan", "isoflavone", "anthocyanin", "catechin", "quercetin", "kaempferol",
    "apigenin", "luteolin", "rutin", "chlorogenic", "caffeic", "ferulic", "p-coumaric",
    "sinapic", "salicylic", "benzoic", "vanillic", "gallic", "ellagic", "eugenol",
    "thymol", "carvacrol", "limonene", "pinene", "cineole", "camphor", "citral",
    "juglone", "sorgoleone", "momilactone", "benzoxazinoid", "dhurrin",
}

KNOWN_HERBICIDE_LIKE_KEYWORDS = {
    "glyphosate", "phosphonate", "phosphinic", "phosphinothricin", "glufosinate",
    "sulfonylurea", "imidazolinone", "triazolopyrimidine", "pyrimidinyl", "benzoate",
    "phenoxy", "auxin", "dinitroaniline", "diphenyl ether", "triazine", "urea", "nitrile",
    "cyclohexanedione", "aryloxyphenoxypropionate", "fop", "dim", "den", "chloroacetamide",
}

TRANSITION_STATE_HINTS = {
    "phosphonate", "phosphate", "sulfonate", "boronate", "hydroxamate", "carboxylate",
    "carboxylic acid", "amide", "urea", "thiourea", "lactone", "epoxide", "oxime",
}

PHOTOSYSTEM_ROS_HINTS = {
    "quinone", "hydroquinone", "phenolic", "phenol", "flavonoid", "anthraquinone", "naphthoquinone",
    "juglone", "paraquat", "diquat", "chlorophyll", "porphyrin",
}


# Coarse phytochemical/chemical-class hooks used for natural-product-aware
# ranking and final portfolio diversity. These are intentionally transparent
# string/rule priors rather than claims of experimentally verified class labels.
PHYTochemical_CLASS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "flavonoid_polyphenol": (
        "flavonoid", "flavone", "flavonol", "quercetin", "kaempferol", "apigenin", "luteolin", "rutin", "catechin", "anthocyanin",
    ),
    "phenolic_acid_or_benzoate": (
        "benzoate", "benzoic", "hydroxybenzoate", "dihydroxybenzoate", "salicylate", "salicylic", "caffeic", "ferulic", "coumaric", "sinapic", "gallic", "vanillic", "chlorogenic",
    ),
    "quinone_redox_candidate": (
        "quinone", "benzoquinone", "toluquinone", "hydroquinone", "naphthoquinone", "anthraquinone", "juglone", "plumbagin",
    ),
    "terpenoid_lipophilic": (
        "terpene", "terpenoid", "limonene", "pinene", "cineole", "camphor", "citral", "thymol", "carvacrol", "eugenol",
    ),
    "alkaloid_nitrogenous": (
        "alkaloid", "pyridine", "quinoline", "isoquinoline", "indole", "nicotin", "berberine", "amine",
    ),
    "glycoside_or_sugar_conjugate": (
        "glycoside", "glucoside", "rutinoside", "rhamnoside", "galactoside", "xyloside",
    ),
    "organophosphonate_transition_state_mimic": (
        "phosphonate", "phosphinic", "phosphinothricin", "glyphosate",
    ),
    "organosulfur_sulfonate": (
        "sulfonate", "sulfinate", "thio", "thiol", "sulfide", "sulfoxide", "sulfone",
    ),
    "organic_acid_or_lactone": (
        "carboxylate", "carboxylic", "lactone", "hydroxyacid", "hydroxy acid", "propanoic acid", "octanoate",
    ),
}



def canonicalize_text_key(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    s = str(value).lower().strip()
    s = re.sub(r"[\u2010-\u2015]", "-", s)
    s = re.sub(r"[:;/,_()\[\]{}]+", " ", s)
    s = re.sub(r"[^a-z0-9+\- ]+", " ", s)
    s = s.replace("coenzyme a", "coa").replace("co-enzyme a", "coa").replace("co enzyme a", "coa")
    s = s.replace("hydroxycinnamoyl-coa", "hydroxycinnamoyl coa").replace("hydroxycinnamoylcoa", "hydroxycinnamoyl coa")
    s = s.replace("hydroxycinnamoyl transferase", "hydroxycinnamoyltransferase")
    s = s.replace("o hydroxycinnamoyl", "hydroxycinnamoyl")
    if "hydroxycinnamoyl" in s and "shikimate" in s and ("transferase" in s or "hydroxycinnamoyltransferase" in s):
        return "hct_hydroxycinnamoyl_coa_shikimate_quinate_transferase"
    s = re.sub(r"\b(isoform|protein|enzyme)\b", " ", s)
    s = re.sub(r"\b\d+[a-z]?\b$", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canonicalize_compound_pair(a: Any, b: Any) -> tuple[str, str]:
    x = canonicalize_text_key(a)
    y = canonicalize_text_key(b)
    pair = sorted([x, y])
    return pair[0], pair[1]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        x = float(value)
        if math.isnan(x) or math.isinf(x):
            return default
        return x
    except Exception:
        return default


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    t = canonicalize_text_key(text)
    return any(canonicalize_text_key(p) in t for p in patterns)


def _smiles_contains_aldehyde(smiles: Any) -> bool:
    s = str(smiles or "")
    # Heuristic, intentionally conservative; real production docking/QSAR can refine this.
    return any(token in s for token in ["C=O", "[CH]=O", "C(=O)[H]"]) and len(s) <= 80


def infer_functional_group_hits(name: Any, smiles: Any = None) -> list[str]:
    text = f"{name or ''} {smiles or ''}".lower()
    hits: list[str] = []
    group_patterns = {
        "phenolic_or_aromatic_hydroxyl": ["phenol", "hydroxy", "catechol", "gallic", "caffeic", "ferulic", "coumaric"],
        "flavonoid_polyphenol": ["flavonoid", "flavone", "flavonol", "quercetin", "kaempferol", "apigenin", "luteolin", "rutin"],
        "terpenoid_lipophilic": ["terpene", "terpenoid", "limonene", "pinene", "cineole", "camphor", "citral", "thymol", "carvacrol"],
        "alkaloid_nitrogenous": ["alkaloid", "pyridine", "indole", "quinoline", "isoquinoline", "amine"],
        "transition_state_acidic_mimic": ["phosphonate", "phosphate", "sulfonate", "boronate", "hydroxamate", "carboxylate"],
        "quinone_ros_redox": ["quinone", "hydroquinone", "juglone", "naphthoquinone", "anthraquinone"],
        "glycoside_or_sugar_conjugate": ["glycoside", "glucoside", "rutinoside", "rhamnoside", "galactoside"],
        "reactive_aldehyde": ["aldehyde", "glyoxal", "methylglyoxal", "lactoaldehyde", "formaldehyde"],
    }
    for key, pats in group_patterns.items():
        if any(p in text for p in pats):
            hits.append(key)
    if _smiles_contains_aldehyde(smiles) and "reactive_aldehyde" not in hits:
        hits.append("reactive_aldehyde")
    return hits



def infer_phytochemical_class(name: Any, smiles: Any = None, source_detail: Any = "") -> tuple[str, float]:
    """Return a coarse phytochemical/chemical class and confidence-like score.

    The label is rule-based and used for diversity-aware candidate selection, not
    as a substitute for LC-MS/NMR structural assignment or curated NP taxonomy.
    """
    text = f"{name or ''} {smiles or ''} {source_detail or ''}".lower()
    best_class = "unclassified_or_unknown"
    best_hits = 0
    for cls, patterns in PHYTochemical_CLASS_KEYWORDS.items():
        hits = sum(1 for pat in patterns if pat in text)
        if hits > best_hits:
            best_class = cls
            best_hits = hits
    if best_hits <= 0:
        return best_class, 0.0
    # Cap at 1.0 while distinguishing single-keyword from multi-keyword evidence.
    return best_class, float(np.clip(0.45 + 0.18 * best_hits, 0.0, 1.0))


@dataclass(frozen=True)
class CompoundAssessment:
    compound_priority_class: str
    compound_exclusion_reason: str
    natural_product_evidence_score: float
    known_inhibitor_similarity_score: float
    functional_group_inhibition_score: float
    transition_state_mimic_score: float
    active_site_compatibility_score: float
    delivery_plausibility_score: float
    solvent_penalty: float
    reactive_aldehyde_penalty: float
    generic_assay_penalty: float
    intervention_suitability_score: float
    phytochemical_class: str
    phytochemical_class_score: float
    functional_group_hits: str
    compound_rule_evidence_class: str = "rule_based_model_inference_with_real_source_evidence"

    def asdict(self) -> dict[str, Any]:
        return asdict(self)


def assess_compound(row: pd.Series | dict[str, Any]) -> CompoundAssessment:
    get = row.get if hasattr(row, "get") else dict(row).get
    name = str(get("compound_name", get("compound_id", "")) or "")
    smiles = get("smiles", "")
    source = str(get("source_resource", "") or "")
    source_detail = str(get("source_detail", "") or "")
    mw = _safe_float(get("mw"), 300.0)
    logp = _safe_float(get("logp"), 1.5)
    tpsa = _safe_float(get("tpsa"), 60.0)
    hbd = _safe_float(get("hbd"), 1.0)
    hba = _safe_float(get("hba"), 3.0)
    key = canonicalize_text_key(name)
    source_key = canonicalize_text_key(source)

    is_fooddb = "fooddb" in source_key
    is_skid = "skid" in source_key
    is_solvent = key in {canonicalize_text_key(x) for x in SOLVENT_OR_VEHICLE_NAMES} or _contains_any(key, SOLVENT_OR_VEHICLE_NAMES)
    is_buffer_or_salt = key in {canonicalize_text_key(x) for x in BUFFER_OR_SALT_NAMES} or _contains_any(key, BUFFER_OR_SALT_NAMES)
    is_reactive_aldehyde = key in {canonicalize_text_key(x) for x in REACTIVE_ALDEHYDE_NAMES} or _contains_any(key, REACTIVE_ALDEHYDE_NAMES) or _smiles_contains_aldehyde(smiles)
    is_assay = key in {canonicalize_text_key(x) for x in COMMON_ASSAY_CHEMICAL_NAMES} or _contains_any(key, COMMON_ASSAY_CHEMICAL_NAMES)

    group_hits = infer_functional_group_hits(name, smiles)
    phytochemical_class, phytochemical_class_score = infer_phytochemical_class(name, smiles, source_detail)
    text = f"{name} {smiles} {source_detail}".lower()

    natural_score = 0.26 + (0.38 if is_fooddb else 0.0) + (0.20 if any(k in text for k in NATURAL_PRODUCT_KEYWORDS) else 0.0)
    natural_score += 0.12 if phytochemical_class != "unclassified_or_unknown" else 0.0
    natural_score += 0.10 if "glycoside_or_sugar_conjugate" in group_hits else 0.0
    natural_score += 0.10 * phytochemical_class_score
    natural_score = float(np.clip(natural_score, 0, 1))

    known_inhibitor_score = 0.15 + (0.55 if any(k in text for k in KNOWN_HERBICIDE_LIKE_KEYWORDS) else 0.0)
    known_inhibitor_score += 0.15 if "transition_state_acidic_mimic" in group_hits else 0.0
    known_inhibitor_score = float(np.clip(known_inhibitor_score, 0, 1))

    fg_score = 0.15 + min(0.55, 0.12 * len([h for h in group_hits if h != "reactive_aldehyde"]))
    if any(h in group_hits for h in ["flavonoid_polyphenol", "phenolic_or_aromatic_hydroxyl", "quinone_ros_redox"]):
        fg_score += 0.15
    fg_score = float(np.clip(fg_score, 0, 1))

    ts_score = 0.10 + (0.45 if any(k in text for k in TRANSITION_STATE_HINTS) else 0.0)
    ts_score += 0.15 if 50 <= tpsa <= 180 and hba >= 2 else 0.0
    ts_score = float(np.clip(ts_score, 0, 1))

    # Herbicides often need intermediate solubility, cellular entry, and target access.
    # This is a delivery proxy, not a regulatory exposure model.
    mw_score = 1.0 - min(1.0, abs(mw - 320.0) / 520.0)
    logp_score = 1.0 - min(1.0, abs(logp - 2.0) / 5.0)
    tpsa_score = 1.0 - min(1.0, abs(tpsa - 90.0) / 160.0)
    delivery = float(np.clip(0.42 * mw_score + 0.34 * logp_score + 0.24 * tpsa_score, 0, 1))

    active_site = float(np.clip(0.35 * fg_score + 0.35 * ts_score + 0.20 * known_inhibitor_score + 0.10 * delivery, 0, 1))

    solvent_penalty = 1.0 if is_solvent else 0.0
    reactive_penalty = 0.85 if is_reactive_aldehyde else 0.0
    assay_penalty = 0.75 if is_assay or is_buffer_or_salt else 0.0
    if is_skid and not is_fooddb:
        assay_penalty = max(assay_penalty, 0.15)

    hazard = _safe_float(get("hazard_proxy"), 0.4)
    persistence = _safe_float(get("persistence_proxy"), 0.4)

    suitability = (
        0.24 * natural_score
        + 0.20 * known_inhibitor_score
        + 0.20 * active_site
        + 0.14 * ts_score
        + 0.14 * fg_score
        + 0.08 * delivery
        + 0.08 * phytochemical_class_score
        - 0.26 * solvent_penalty
        - 0.23 * reactive_penalty
        - 0.18 * assay_penalty
        - 0.12 * hazard
        - 0.08 * persistence
    )
    suitability = float(np.clip(suitability, 0, 1))

    exclusion_reasons: list[str] = []
    priority = "low_priority_unknown"
    if is_solvent:
        priority = "solvent_or_vehicle_control"
        exclusion_reasons.append("common_solvent_or_vehicle")
    elif is_buffer_or_salt:
        priority = "generic_assay_chemical"
        exclusion_reasons.append("buffer_salt_or_generic_medium_component")
    elif is_reactive_aldehyde:
        priority = "reactive_toxic_aldehyde_control"
        exclusion_reasons.append("highly_reactive_small_aldehyde_control_only")
    elif is_assay:
        priority = "generic_assay_chemical"
        exclusion_reasons.append("generic_metabolite_or_assay_chemical")
    elif known_inhibitor_score >= 0.55:
        priority = "known_inhibitor_like"
    elif ts_score >= 0.55:
        priority = "transition_state_mimic_candidate"
    elif phytochemical_class in {"flavonoid_polyphenol", "phenolic_acid_or_benzoate", "terpenoid_lipophilic", "alkaloid_nitrogenous", "glycoside_or_sugar_conjugate"} and natural_score >= 0.46 and fg_score >= 0.30:
        priority = "allelopathic_secondary_metabolite"
    elif phytochemical_class == "quinone_redox_candidate" or any(k in text for k in PHOTOSYSTEM_ROS_HINTS):
        priority = "oxidative_stress_inducer_candidate"
    elif natural_score >= 0.48 or phytochemical_class_score >= 0.45:
        priority = "natural_product_candidate"

    if suitability < 0.20 and not exclusion_reasons:
        exclusion_reasons.append("low_intervention_suitability_score")

    return CompoundAssessment(
        compound_priority_class=priority,
        compound_exclusion_reason=";".join(exclusion_reasons) if exclusion_reasons else "",
        natural_product_evidence_score=natural_score,
        known_inhibitor_similarity_score=known_inhibitor_score,
        functional_group_inhibition_score=fg_score,
        transition_state_mimic_score=ts_score,
        active_site_compatibility_score=active_site,
        delivery_plausibility_score=delivery,
        solvent_penalty=float(solvent_penalty),
        reactive_aldehyde_penalty=float(reactive_penalty),
        generic_assay_penalty=float(assay_penalty),
        intervention_suitability_score=suitability,
        phytochemical_class=phytochemical_class,
        phytochemical_class_score=float(phytochemical_class_score),
        functional_group_hits=";".join(sorted(group_hits)),
    )


def annotate_compound_pool(cp: pd.DataFrame) -> pd.DataFrame:
    if cp is None or not len(cp):
        return pd.DataFrame()
    out = cp.copy()
    assessments = out.apply(lambda r: assess_compound(r).asdict(), axis=1).apply(pd.Series)
    out = pd.concat([out.reset_index(drop=True), assessments.reset_index(drop=True)], axis=1)
    return out


def pair_diversity_key(row: pd.Series) -> str:
    a_class = str(row.get("compound_a_priority_class", ""))
    b_class = str(row.get("compound_b_priority_class", ""))
    return "||".join(sorted([a_class, b_class]))



def pair_phytochemical_class_key(row: pd.Series | dict[str, Any]) -> str:
    get = row.get if hasattr(row, "get") else dict(row).get
    a_class = str(get("compound_a_phytochemical_class", "unclassified_or_unknown") or "unclassified_or_unknown")
    b_class = str(get("compound_b_phytochemical_class", "unclassified_or_unknown") or "unclassified_or_unknown")
    return "||".join(sorted([a_class, b_class]))
