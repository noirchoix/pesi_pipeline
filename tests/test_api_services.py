from pesi.api.config import get_settings
from pesi.api.services.artifact_reader import ArtifactReader
from pesi.api.services.interpretation_service import InterpretationService


def test_artifact_reader_falls_back_to_medium_outputs():
    settings = get_settings()
    reader = ArtifactReader(settings)
    summary = reader.benchmark_summary()
    assert summary["status"] == "ok"
    assert "production_gate_summary" in summary


def test_interpretation_includes_mandatory_caveats():
    settings = get_settings()
    data = InterpretationService(settings).interpret_run()
    caveats = data["caveats"]
    assert "Computational candidate only." in caveats
    assert data["evidence_policy"].startswith("Grounded only")
