"""Every response says how long the API took, so a slow screen can be traced to the API or to the network."""

from fastapi.testclient import TestClient

from app.main import app


def test_a_response_reports_its_time():
    res = TestClient(app).get("/health")
    assert res.status_code == 200
    assert res.headers["server-timing"].startswith("api;dur=")
