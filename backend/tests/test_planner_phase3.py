"""Tests for phase-3 planner and recommendation endpoints."""

from fastapi.testclient import TestClient


def _sample_plan_request(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "constraints": {
            "calories_target": 2100,
            "protein_g_target": 130,
            "dietary_restrictions": ["vegetarian"],
            "allergies": ["peanut"],
            "max_cook_time_minutes": 20,
        },
        "inventory": {
            "user_id": user_id,
            "items": [
                {"ingredient": "tofu", "quantity": "400g", "expires_in_days": 2},
                {"ingredient": "spinach", "quantity": "1 bunch", "expires_in_days": 1},
            ],
        },
        "user_message": "Use expiring ingredients first",
    }


def test_planner_requires_auth(client: TestClient) -> None:
    response = client.post("/api/v1/planner/recommendations", json=_sample_plan_request("planner-1"))
    assert response.status_code == 401


def test_planner_create_and_read_latest_bundle(client: TestClient) -> None:
    user_id = "planner-1"
    headers = {"Authorization": "Bearer fake-token", "X-Test-User-Id": user_id}

    created = client.post("/api/v1/planner/recommendations", json=_sample_plan_request(user_id), headers=headers)
    assert created.status_code == 200
    body = created.json()
    assert body["recommendation_id"]
    assert body["recipe_title"]
    assert body["nutrition_summary"]["calories"] >= 1

    latest = client.get(f"/api/v1/planner/recommendations/latest/{user_id}", headers=headers)
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["recommendation_id"] == body["recommendation_id"]


def test_planner_detail_views(client: TestClient) -> None:
    user_id = "planner-2"
    headers = {"Authorization": "Bearer fake-token", "X-Test-User-Id": user_id}

    created = client.post("/api/v1/planner/recommendations", json=_sample_plan_request(user_id), headers=headers)
    recommendation_id = created.json()["recommendation_id"]

    recipe = client.get(f"/api/v1/planner/recommendations/{recommendation_id}/recipe", headers=headers)
    nutrition = client.get(f"/api/v1/planner/recommendations/{recommendation_id}/nutrition", headers=headers)
    gap = client.get(f"/api/v1/planner/recommendations/{recommendation_id}/grocery-gap", headers=headers)

    assert recipe.status_code == 200
    assert nutrition.status_code == 200
    assert gap.status_code == 200

    assert recipe.json()["recipe_title"]
    assert nutrition.json()["calories"] >= 1
    assert isinstance(gap.json(), list)
