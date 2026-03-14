"""Tests for Cognito callback endpoint behavior."""

from fastapi.testclient import TestClient


def test_cognito_callback_requires_code(client: TestClient) -> None:
    response = client.get("/api/v1/auth/cognito/callback")

    assert response.status_code == 400
    body = response.json()
    assert body["code"]
    assert body["trace_id"]


def test_cognito_callback_success(client: TestClient) -> None:
    response = client.get("/api/v1/auth/cognito/callback?code=abc123&state=xyz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "callback_received"
    assert body["authorization_code"] == "abc123"
    assert body["state"] == "xyz"
