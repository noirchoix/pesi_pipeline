from pesi.domain.synergy import score_pair_synergy


def test_synergy_schema_generated():
    target = {"enzyme_name": "acetolactate synthase", "enzyme_family": "ALS/AHAS", "stage_assigned": "seedling_emergence", "herbicide_target_score": 0.9}
    a = {"compound_name": "quercetin", "source_resource": "FoodDB", "intervention_suitability_score": 0.8, "active_site_compatibility_score": 0.7, "known_inhibitor_similarity_score": 0.3, "transition_state_mimic_score": 0.4, "functional_group_inhibition_score": 0.8, "natural_product_evidence_score": 0.9}
    b = {"compound_name": "ferulic acid", "source_resource": "FoodDB", "intervention_suitability_score": 0.7, "active_site_compatibility_score": 0.6, "known_inhibitor_similarity_score": 0.2, "transition_state_mimic_score": 0.5, "functional_group_inhibition_score": 0.7, "natural_product_evidence_score": 0.8}
    s = score_pair_synergy(target, a, b, epsilon=0.5)
    assert s["synergy_group_score"] >= 0
    assert "synergy_match_schema" in s
