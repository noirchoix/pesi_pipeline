from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pesi.domain.compound_rules import canonicalize_text_key


@dataclass(frozen=True)
class HerbicideTargetRule:
    target_family: str
    site_of_action: str
    target_patterns: tuple[str, ...]
    wssa_group: str
    pathway: str
    known_inhibitor_classes: tuple[str, ...]
    binding_logic: str
    active_stages: tuple[str, ...]
    selectivity_mechanisms: tuple[str, ...]
    resistance_risks: tuple[str, ...]
    evidence_class: str = "literature_rule"

    def asdict(self) -> dict[str, Any]:
        d = asdict(self)
        for k, v in list(d.items()):
            if isinstance(v, tuple):
                d[k] = ";".join(v)
        return d


HERBICIDE_TARGET_RULES: tuple[HerbicideTargetRule, ...] = (
    HerbicideTargetRule(
        target_family="ACCase",
        site_of_action="acetyl-CoA carboxylase",
        target_patterns=("accase", "acetyl coa carboxylase", "acetyl-coa carboxylase", "carboxylase"),
        wssa_group="1",
        pathway="fatty_acid_biosynthesis",
        known_inhibitor_classes=("aryloxyphenoxypropionates/fops", "cyclohexanediones/dims", "phenylpyrazolines/dens"),
        binding_logic="active_site_or_carboxyltransferase_domain_inhibition",
        active_stages=("vegetative_expansion", "early_vegetative", "meristematic_growth"),
        selectivity_mechanisms=("crop_metabolism", "target_site_insensitivity", "meristem_access"),
        resistance_risks=("target_site_mutation", "enhanced_metabolism"),
    ),
    HerbicideTargetRule(
        target_family="ALS/AHAS",
        site_of_action="acetolactate synthase / acetohydroxyacid synthase",
        target_patterns=("als", "ahas", "acetolactate", "acetohydroxyacid"),
        wssa_group="2",
        pathway="branched_chain_amino_acid_biosynthesis",
        known_inhibitor_classes=("sulfonylureas", "imidazolinones", "triazolopyrimidines", "pyrimidinyl-thiobenzoates"),
        binding_logic="active_site/allosteric_channel_binding_slowing_branched_chain_amino_acid_synthesis",
        active_stages=("seedling_emergence", "early_vegetative"),
        selectivity_mechanisms=("differential_metabolism", "target_site_sensitivity", "growth_stage"),
        resistance_risks=("target_site_mutation", "metabolic_resistance", "cross_resistance"),
    ),
    HerbicideTargetRule(
        target_family="EPSPS",
        site_of_action="5-enolpyruvylshikimate-3-phosphate synthase",
        target_patterns=("epsp", "epsps", "shikimate", "5-enolpyruvylshikimate"),
        wssa_group="9",
        pathway="shikimate_aromatic_amino_acid_biosynthesis",
        known_inhibitor_classes=("glyphosate-like phosphonate transition-state/substrate mimics",),
        binding_logic="substrate/transition_state_mimicry_at_shikimate_pathway_enzyme",
        active_stages=("early_vegetative", "seedling_emergence"),
        selectivity_mechanisms=("herbicide_tolerant_crop_trait", "target_overexpression", "differential_translocation"),
        resistance_risks=("target_site_mutation", "target_amplification", "reduced_translocation"),
    ),
    HerbicideTargetRule(
        target_family="Glutamine synthetase",
        site_of_action="glutamine synthetase",
        target_patterns=("glutamine synthetase", "gs"),
        wssa_group="10",
        pathway="nitrogen_assimilation",
        known_inhibitor_classes=("glufosinate/phosphinothricin-like",),
        binding_logic="amino_acid_analog_inhibition_causing_ammonia_accumulation_and_photosynthetic_disruption",
        active_stages=("early_vegetative", "vegetative_expansion"),
        selectivity_mechanisms=("crop_trait", "differential_detoxification"),
        resistance_risks=("target_site_insensitivity", "enhanced_metabolism"),
    ),
    HerbicideTargetRule(
        target_family="PPO",
        site_of_action="protoporphyrinogen oxidase",
        target_patterns=("ppo", "protoporphyrinogen", "protox"),
        wssa_group="14",
        pathway="tetrapyrrole_chlorophyll_biosynthesis",
        known_inhibitor_classes=("diphenyl ethers", "n-phenylphthalimides", "triazolinones", "oxadiazoles"),
        binding_logic="active_site_inhibition_leading_to_photodynamic_ros_lipid_peroxidation",
        active_stages=("vegetative_expansion", "photosynthetic_establishment"),
        selectivity_mechanisms=("differential_metabolism", "foliar_retention", "light_activation"),
        resistance_risks=("target_site_mutation", "enhanced_metabolism"),
    ),
    HerbicideTargetRule(
        target_family="PSII",
        site_of_action="photosystem II electron transport, QB binding protein/site",
        target_patterns=("photosystem ii", "psii", "qb binding", "d1 protein", "photosynthesis"),
        wssa_group="5/6/7",
        pathway="photosynthetic_electron_transport",
        known_inhibitor_classes=("triazines", "ureas", "nitriles", "benzothiadiazinones", "phenylcarbamates"),
        binding_logic="non_enzyme_target_electron_transport_block_generating_phototoxic_stress",
        active_stages=("photosynthetic_establishment", "vegetative_expansion"),
        selectivity_mechanisms=("crop_metabolism", "leaf_uptake", "differential_photosynthetic_stress_response"),
        resistance_risks=("psbA_target_site_mutation", "enhanced_metabolism"),
    ),
    HerbicideTargetRule(
        target_family="PSI",
        site_of_action="photosystem I electron diversion",
        target_patterns=("photosystem i", "psi", "ferredoxin", "electron diverter"),
        wssa_group="22",
        pathway="photosynthetic_electron_transport",
        known_inhibitor_classes=("bipyridyliums", "paraquat/diquat-like redox cyclers"),
        binding_logic="electron_acceptor_redox_cycling_generating_ros",
        active_stages=("photosynthetic_establishment", "vegetative_expansion"),
        selectivity_mechanisms=("spray_contact", "cuticle_penetration", "antioxidant_capacity"),
        resistance_risks=("sequestration", "reduced_translocation", "antioxidant_response"),
    ),
    HerbicideTargetRule(
        target_family="Tubulin/microtubule",
        site_of_action="microtubule assembly / tubulin polymerization",
        target_patterns=("tubulin", "microtubule", "cell division", "mitosis"),
        wssa_group="3",
        pathway="cell_division",
        known_inhibitor_classes=("dinitroanilines",),
        binding_logic="microtubule_assembly_inhibition_at_meristematic_growth_zones",
        active_stages=("germination", "seedling_emergence"),
        selectivity_mechanisms=("herbicide_layer_depth", "meristem_position", "seed_lipid_partitioning"),
        resistance_risks=("tubulin_target_site_mutation", "application_escape"),
    ),
    HerbicideTargetRule(
        target_family="VLCFA",
        site_of_action="very long chain fatty acid biosynthesis elongase system",
        target_patterns=("vlcfa", "very long chain fatty acid", "fatty acid elongase", "kcs", "3-ketoacyl-coa synthase"),
        wssa_group="15/8",
        pathway="very_long_chain_fatty_acid_and_cuticular_wax_biosynthesis",
        known_inhibitor_classes=("chloroacetamides", "thiocarbamates"),
        binding_logic="inhibition_of_fatty_acid_elongation_affecting_seedling_shoot_growth_and_waxes",
        active_stages=("germination", "seedling_emergence"),
        selectivity_mechanisms=("soil_positioning", "coleoptile_access", "crop_planting_depth"),
        resistance_risks=("enhanced_metabolism", "reduced_uptake"),
    ),
    HerbicideTargetRule(
        target_family="CAZy/cell wall",
        site_of_action="cell wall carbohydrate metabolism / cellulose-associated enzymes",
        target_patterns=("cellulase", "cellulose", "glycoside hydrolase", "cazy", "glucan", "cell wall"),
        wssa_group="20/unknown",
        pathway="cell_wall_biosynthesis_and_remodeling",
        known_inhibitor_classes=("cell_wall_synthesis_inhibitors", "glycosidase_inhibitor_like"),
        binding_logic="substrate_cleft_or_tunnel_binding_in_cell_wall_remodeling_enzymes",
        active_stages=("germination", "cell_wall_secondary_growth", "seedling_emergence"),
        selectivity_mechanisms=("growth_stage", "cell_wall_flux", "tissue_access"),
        resistance_risks=("pathway_bypass", "reduced_uptake"),
    ),
    HerbicideTargetRule(
        target_family="CYP450 detoxification",
        site_of_action="cytochrome P450 herbicide metabolism and specialized metabolism",
        target_patterns=("cytochrome p450", "p450", "cyp"),
        wssa_group="detoxification_modifier",
        pathway="xenobiotic_and_secondary_metabolism",
        known_inhibitor_classes=("p450_inhibitors", "synergist_candidates"),
        binding_logic="metabolic_resistance_or_safener_context; inhibition can modify detoxification rather than direct primary target death",
        active_stages=("specialized_metabolism", "stress_response"),
        selectivity_mechanisms=("crop_detox_capacity", "weed_metabolic_resistance", "secondary_metabolite_context"),
        resistance_risks=("metabolic_resistance", "cross_resistance"),
    ),
    HerbicideTargetRule(
        target_family="Oxidative stress enzymes",
        site_of_action="SOD/CAT/POD/peroxidase antioxidant stress response",
        target_patterns=("peroxidase", "catalase", "superoxide dismutase", "sod", "cat", "pod", "oxidative stress"),
        wssa_group="stress_response_modifier",
        pathway="ros_homeostasis",
        known_inhibitor_classes=("redox_active_phytochemicals", "photosensitizers", "quinone_like"),
        binding_logic="stress_amplification_or_antioxidant_response_distortion",
        active_stages=("stress_response", "photosynthetic_establishment"),
        selectivity_mechanisms=("differential_antioxidant_capacity", "exposure_dose", "growth_stage"),
        resistance_risks=("antioxidant_upregulation", "metabolic_resistance"),
    ),
)


def load_reference_csv(path: Path | None = None) -> list[dict[str, str]]:
    if path is None:
        cwd_path = Path.cwd() / "data" / "reference" / "herbicide_target_reference.csv"
        path = cwd_path if cwd_path.exists() else None
    if path is None or not path.exists():
        return [r.asdict() for r in HERBICIDE_TARGET_RULES]
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def export_reference_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [r.asdict() for r in HERBICIDE_TARGET_RULES]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def match_herbicide_targets(enzyme_name: Any, enzyme_family: Any = "", stage: Any = "") -> dict[str, Any]:
    text = f"{enzyme_name or ''} {enzyme_family or ''}".lower()
    canon = canonicalize_text_key(text)
    best: HerbicideTargetRule | None = None
    best_score = 0.0
    hits: list[str] = []
    for rule in HERBICIDE_TARGET_RULES:
        score = 0.0
        for pat in rule.target_patterns:
            p = canonicalize_text_key(pat)
            if p and p in canon:
                score += 0.55
                hits.append(pat)
        if canonicalize_text_key(rule.target_family) in canonicalize_text_key(str(enzyme_family)):
            score += 0.35
        if stage and str(stage) in rule.active_stages:
            score += 0.10
        score = float(np.clip(score, 0, 1))
        if score > best_score:
            best_score = score
            best = rule
    if best is None:
        return {
            "herbicide_target_family": "unmapped",
            "herbicide_site_of_action": "unmapped",
            "herbicide_target_score": 0.0,
            "known_inhibitor_classes": "",
            "wssa_group": "unmapped",
            "resistance_risks": "",
            "selectivity_mechanisms": "",
            "target_rule_evidence_class": "unmapped_model_inference",
        }
    return {
        "herbicide_target_family": best.target_family,
        "herbicide_site_of_action": best.site_of_action,
        "herbicide_target_score": best_score,
        "known_inhibitor_classes": ";".join(best.known_inhibitor_classes),
        "wssa_group": best.wssa_group,
        "resistance_risks": ";".join(best.resistance_risks),
        "selectivity_mechanisms": ";".join(best.selectivity_mechanisms),
        "binding_logic": best.binding_logic,
        "target_rule_evidence_class": best.evidence_class if best_score > 0 else "unmapped_model_inference",
    }
