"""Tests for phase-5 observability and error envelope behavior."""

from fastapi.testclient import TestClient


def test_trace_id_header_is_added(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers.get("x-trace-id")


def test_trace_id_header_is_propagated(client: TestClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Trace-Id": "trace-from-client-1"})

    assert response.status_code == 200
    assert response.headers.get("x-trace-id") == "trace-from-client-1"


def test_http_errors_use_problem_response(client: TestClient) -> None:
    response = client.get("/api/v1/profiles/user-ob-1")

    assert response.status_code == 401
    body = response.json()
    assert body["code"]
    assert body["message"]
    assert body["trace_id"] == response.headers.get("x-trace-id")
    assert isinstance(body["retryable"], bool)


def test_validation_errors_use_problem_response(client: TestClient) -> None:
    headers = {"Authorization": "Bearer fake-token", "X-Test-User-Id": "user-ob-2"}
    response = client.post("/api/v1/inputs/chat-message", json={}, headers=headers)

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["trace_id"] == response.headers.get("x-trace-id")
