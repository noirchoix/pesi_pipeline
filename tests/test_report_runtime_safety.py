from __future__ import annotations

import json
import math

from fastapi.testclient import TestClient

from pesi.api.config import ApiSettings
from pesi.api.main import app
from pesi.api.services.json_safe import to_json_safe
from pesi.api.services.llm_client import DeepSeekClient
from pesi.api.services.report_interpreter import ReportInterpreter


def test_to_json_safe_removes_nested_non_finite_values() -> None:
    payload = {
        "nan": float("nan"),
        "pos_inf": float("inf"),
        "nested": [1.0, {"neg_inf": float("-inf")}],
    }
    safe = to_json_safe(payload)
    assert safe == {"nan": None, "pos_inf": None, "nested": [1.0, {"neg_inf": None}]}
    json.dumps(safe, allow_nan=False)


def test_report_interpreter_sanitizes_full_report_payload() -> None:
    settings = ApiSettings(project_root=".", ai_enabled=False)
    interpreter = ReportInterpreter(settings)
    recommendation = {
        "id": "r1",
        "compound_a": "Compound A",
        "compound_b": "Compound B",
        "target": "EPSP synthase",
        "target_family": "EPSPS",
        "stage": "Seedling emergence",
        "evidence_strength": "Strong review lead",
        "validation_note": "Validate experimentally.",
        "raw_scores": {"review_fit": float("nan"), "pairing_support": float("inf")},
    }
    evidence = {
        "path": [],
        "enzyme_state_reasoning": {
            "growth_stage": "seedling_emergence",
            "target_class": "curated_family_function",
            "evidence_signals": {"pathway_essentiality": 0.9, "kinetic_evidence": float("nan")},
        },
        "scenario_selectivity": {"selectivity_margin": float("inf")},
        "assay_prioritization": {
            "status": "available",
            "relative_input_band": [0.6, float("nan")],
            "simulated_max_inhibition": float("nan"),
        },
        "confidence_and_limitations": {},
    }
    report = interpreter.aggregate(
        scenario={"crop": "Zea mays", "weed": "Amaranthus palmeri", "growth_stage": "seedling_emergence"},
        recommendations=[recommendation],
        targets=[],
        evidence_by_recommendation={"r1": evidence},
        target_reasoning=[],
        pair_food_details={},
        report_type="full",
        caveats=[],
        food_mapping={"coverage": float("nan")},
    )
    json.dumps(report, allow_nan=False)
    html = interpreter.render_html(report)
    assert "NaN" not in html
    assert "Infinity" not in html


def test_full_report_endpoint_is_json_compliant() -> None:
    client = TestClient(app)
    response = client.post(
        "/api/v1/inference/reports",
        json={
            "report_type": "full",
            "format": "json",
            "scenario": {"crop": "Zea mays", "weed": "Amaranthus palmeri", "growth_stage": "seedling_emergence"},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["report_type"] == "full"
    json.dumps(payload, allow_nan=False)


def test_deepseek_client_reports_configured_and_parses_json(monkeypatch) -> None:
    settings = ApiSettings(
        project_root=".",
        ai_enabled=True,
        ai_provider="deepseek",
        deepseek_api_key="test-key",
        deepseek_model="deepseek-chat",
    )
    client = DeepSeekClient(settings)
    assert client.configuration_status()["status"] == "configured"

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return {"choices": [{"message": {"content": '{"status":"ok","title":"Grounded"}'}}]}

    monkeypatch.setattr("pesi.api.services.llm_client.requests.post", lambda *args, **kwargs: Response())
    result = client.complete_json(system="Return JSON.", user='{"evidence":"grounded"}', fallback={"status": "fallback"})
    assert result["ai_source"] == "deepseek"
    assert result["ai_status"] == "generated"
    assert result["title"] == "Grounded"
