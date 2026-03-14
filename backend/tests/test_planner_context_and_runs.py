"""Tests for intelligent context assembly and plan run trace tracking."""

from fastapi.testclient import TestClient


def test_planner_uses_persisted_context_and_exposes_latest_run(client: TestClient) -> None:
    user_id = "ctx-user-1"
    headers = {"Authorization": "Bearer fake-token", "X-Test-User-Id": user_id}

    goals_payload = {
        "calories_target": 2100,
        "protein_g_target": 130,
        "carbs_g_target": 220,
        "fat_g_target": 70,
        "dietary_restrictions": ["vegetarian"],
        "allergies": ["peanut"],
        "budget_limit": 28,
        "max_cook_time_minutes": 20,
    }
    upsert_goals = client.put(f"/api/v1/goals/{user_id}", json=goals_payload, headers=headers)
    assert upsert_goals.status_code == 200

    fridge_payload = {
        "image_url": "https://example.com/fridge.jpg",
        "detected_items": [
            {"ingredient": "spinach", "quantity": "1 bunch", "expires_in_days": 1},
            {"ingredient": "tofu", "quantity": "400g", "expires_in_days": 2},
        ],
    }
    fridge_job = client.post("/api/v1/inputs/fridge-scan", json=fridge_payload, headers=headers)
    assert fridge_job.status_code == 202

    chat_payload = {"message": "Use expiring ingredients first"}
    chat_event = client.post("/api/v1/inputs/chat-message", json=chat_payload, headers=headers)
    assert chat_event.status_code == 200

    # Empty constraints + no inventory => planner should enrich from DB context.
    plan_request = {
        "user_id": user_id,
        "constraints": {},
    }
    created = client.post("/api/v1/planner/recommendations", json=plan_request, headers=headers)
    assert created.status_code == 200
    assert created.json()["recommendation_id"]

    latest_run = client.get(f"/api/v1/planner/runs/latest/{user_id}", headers=headers)
    assert latest_run.status_code == 200
    run_body = latest_run.json()
    assert run_body["status"] == "COMPLETED"
    assert run_body["mode"] in ["adk", "fallback"]
    assert isinstance(run_body["trace_notes"], list)
    assert run_body["trace_notes"]
