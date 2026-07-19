from __future__ import annotations

from urllib.parse import quote

from fastapi.testclient import TestClient

from pesi.api.main import app


def test_food_source_and_evidence_endpoints() -> None:
    client = TestClient(app)
    results_res = client.get("/api/v1/inference/results", params={"limit": 5})
    assert results_res.status_code == 200
    results = results_res.json()
    recommendation = results["recommendations"][0]
    target = results["targets"][0]

    evidence_res = client.get(
        f"/api/v1/inference/recommendations/{quote(recommendation['id'], safe='')}/evidence-path"
    )
    assert evidence_res.status_code == 200
    assert evidence_res.json()["status"] == "ok"

    state_res = client.get(
        f"/api/v1/inference/targets/{quote(target['id'], safe='')}/state-reasoning"
    )
    assert state_res.status_code == 200
    assert "evidence_signals" in state_res.json()

    compound_res = client.get(
        "/api/v1/inference/food-sources/compound",
        params={"compound": "3,4-dihydroxybenzoate", "limit": 5},
    )
    assert compound_res.status_code == 200
    payload = compound_res.json()
    assert payload["status"] == "ok"
    assert payload["match_status"] in {"matched", "ambiguous", "unmatched"}
    assert payload["source_count_returned"] == len(payload["sources"])
    if payload["match_status"] != "matched":
        assert payload["sources"] == []
        assert payload["source_suppressed"] is True

    report_res = client.get("/api/v1/results/food-source-report")
    assert report_res.status_code == 200
    assert report_res.json()["status"] in {"completed", "missing"}
