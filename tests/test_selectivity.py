from pesi.domain.selectivity import estimate_contextual_selectivity
from pesi.schemas.scenario import FieldScenario


def test_selectivity_report_keys():
    scenario = FieldScenario(crop_taxa=["Triticum aestivum"], weed_taxa=["Ageratum conyzoides"], growth_stage="seedling_emergence")
    out = estimate_contextual_selectivity({"enzyme_name": "acetolactate synthase", "enzyme_family": "ALS/AHAS", "stage_assigned": "seedling_emergence"}, scenario)
    assert "scenario_selectivity_margin" in out
    assert 0 <= out["scenario_selectivity_margin"] <= 1
