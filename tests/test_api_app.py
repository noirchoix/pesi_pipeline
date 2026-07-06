from fastapi.testclient import TestClient

from pesi.api.main import app


def test_health_endpoint():
    client = TestClient(app)
    res = client.get('/api/v1/health')
    assert res.status_code == 200
    assert res.json()['status'] == 'ok'


def test_benchmark_summary_endpoint():
    client = TestClient(app)
    res = client.get('/api/v1/benchmarks/summary')
    assert res.status_code == 200
    assert 'production_gate_summary' in res.json()
