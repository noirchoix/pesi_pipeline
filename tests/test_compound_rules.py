from pesi.domain.compound_rules import assess_compound, canonicalize_compound_pair


def test_solvent_downranked():
    a = assess_compound({"compound_name": "ethanol", "source_resource": "FoodDB", "mw": 46, "logp": -0.3, "tpsa": 20})
    assert a.compound_priority_class == "solvent_or_vehicle_control"
    assert a.solvent_penalty == 1.0
    assert a.intervention_suitability_score < 0.5


def test_natural_polyphenol_prioritized():
    a = assess_compound({"compound_name": "quercetin", "source_resource": "FoodDB", "mw": 302, "logp": 1.5, "tpsa": 130})
    assert a.compound_priority_class in {"allelopathic_secondary_metabolite", "natural_product_candidate"}
    assert a.natural_product_evidence_score >= 0.5


def test_compound_pair_unordered():
    assert canonicalize_compound_pair("ethanol", "methylglyoxal") == canonicalize_compound_pair("methylglyoxal", "ethanol")
