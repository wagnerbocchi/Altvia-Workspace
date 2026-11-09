from altvia.main import create_app
from fastapi.testclient import TestClient


def test_liveness_discloses_only_service_status():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_unauthenticated_identity_request_returns_problem_not_redirect():
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "authentication_required"
