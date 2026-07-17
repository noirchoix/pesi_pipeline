from __future__ import annotations

import json

from pesi.api.config import ApiSettings
from pesi.api.services.artifact_reader import ArtifactReader


def test_unscoped_artifact_read_falls_back_when_primary_file_is_missing(tmp_path):
    (tmp_path / "outputs").mkdir()
    medium = tmp_path / "outputs_medium"
    medium.mkdir()
    payload = {"status": "completed", "recommended_match_coverage": 0.6154}
    (medium / "food_source_mapping_report.json").write_text(json.dumps(payload), encoding="utf-8")

    settings = ApiSettings(
        project_root=tmp_path,
        default_out_dir="outputs",
        fallback_out_dir="outputs_medium",
    )
    report = ArtifactReader(settings).read_json("food-source-report")

    assert report == payload


def test_run_scoped_artifact_read_does_not_leak_from_fallback(tmp_path):
    run_outputs = tmp_path / "run_outputs"
    run_outputs.mkdir()
    medium = tmp_path / "outputs_medium"
    medium.mkdir()
    (medium / "food_source_mapping_report.json").write_text(
        json.dumps({"status": "completed"}), encoding="utf-8"
    )

    settings = ApiSettings(
        project_root=tmp_path,
        default_out_dir="outputs",
        fallback_out_dir="outputs_medium",
    )
    report = ArtifactReader(settings).read_json("food-source-report", "run_outputs")

    assert report["status"] == "missing"
    assert report["path"].endswith("run_outputs/food_source_mapping_report.json") or report["path"].endswith("run_outputs\\food_source_mapping_report.json")
