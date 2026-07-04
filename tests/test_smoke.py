from pesi.etl.loaders import CORE_STAGE_ANCHORS

def test_stage_anchors_exist():
    assert len(CORE_STAGE_ANCHORS) >= 8
