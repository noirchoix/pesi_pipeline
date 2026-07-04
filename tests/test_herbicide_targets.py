from pesi.domain.herbicide_targets import HERBICIDE_TARGET_RULES, match_herbicide_targets


def test_target_atlas_has_core_modes():
    families = {r.target_family for r in HERBICIDE_TARGET_RULES}
    for expected in ["ALS/AHAS", "EPSPS", "ACCase", "PPO", "PSII", "PSI", "VLCFA"]:
        assert expected in families


def test_match_als():
    m = match_herbicide_targets("acetolactate synthase", "ALS/AHAS", "seedling_emergence")
    assert m["herbicide_target_family"] == "ALS/AHAS"
    assert m["herbicide_target_score"] > 0
