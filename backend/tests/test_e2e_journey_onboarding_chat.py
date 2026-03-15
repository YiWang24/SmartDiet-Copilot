"""Journey-oriented E2E tests for onboarding and chat stages."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_e2e_01_first_time_onboarding_roundtrip(client: TestClient, auth_headers) -> None:
    """E2E-01: user can create/read profile and goals."""

    user_id = "journey-onboard-1"
    headers = auth_headers(user_id)

    profile_payload = {
        "age": 29,
        "height_cm": 171.5,
        "weight_kg": 63.2,
        "activity_level": "moderate",
        "dietary_preferences": ["vegetarian"],
        "allergies": ["peanut"],
        "cook_time_preference_minutes": 20,
    }
    goals_payload = {
        "calories_target": 2100,
        "protein_g_target": 130,
        "carbs_g_target": 220,
        "fat_g_target": 70,
        "dietary_restrictions": ["vegetarian"],
        "allergies": ["peanut"],
        "budget_limit": 28.5,
        "max_cook_time_minutes": 25,
    }

    upsert_profile = client.put(f"/api/v1/profiles/{user_id}", json=profile_payload, headers=headers)
    assert upsert_profile.status_code == 200
    upsert_goals = client.put(f"/api/v1/goals/{user_id}", json=goals_payload, headers=headers)
    assert upsert_goals.status_code == 200

    profile = client.get(f"/api/v1/profiles/{user_id}", headers=headers)
    goals = client.get(f"/api/v1/goals/{user_id}", headers=headers)
    assert profile.status_code == 200
    assert goals.status_code == 200
    assert profile.json()["dietary_preferences"] == ["vegetarian"]
    assert goals.json()["max_cook_time_minutes"] == 25


def test_e2e_02_update_onboarding_later(client: TestClient, auth_headers) -> None:
    """E2E-02: user can update onboarding constraints later."""

    user_id = "journey-onboard-2"
    headers = auth_headers(user_id)

    first = client.put(
        f"/api/v1/goals/{user_id}",
        json={"calories_target": 2000, "dietary_restrictions": ["vegetarian"]},
        headers=headers,
    )
    assert first.status_code == 200

    second = client.put(
        f"/api/v1/goals/{user_id}",
        json={"calories_target": 1700, "dietary_restrictions": ["vegetarian", "gluten-free"]},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["calories_target"] == 1700
    assert "gluten-free" in second.json()["dietary_restrictions"]


def test_e2e_06_chat_message_persist_and_latest_read(client: TestClient, auth_headers) -> None:
    """E2E-06: chat-only planning refinement persists and is queryable."""

    user_id = "journey-chat-1"
    headers = auth_headers(user_id)

    post = client.post(
        "/api/v1/inputs/chat-message",
        json={"message": "Make it vegetarian and under 500 calories"},
        headers=headers,
    )
    assert post.status_code == 200
    assert post.json()["message"] == "Make it vegetarian and under 500 calories"

    latest = client.get("/api/v1/inputs/chat-messages/latest?limit=5", headers=headers)
    assert latest.status_code == 200
    events = latest.json()
    assert len(events) >= 1
    assert events[0]["message"] == "Make it vegetarian and under 500 calories"
    assert events[0]["role"] == "user"


def test_e2e_06_chat_auto_replan_persists_assistant_turn(client: TestClient, auth_headers) -> None:
    """Chat with auto_replan stores assistant turn and recommendation for history reload."""

    user_id = "journey-chat-2"
    headers = auth_headers(user_id)

    post = client.post(
        "/api/v1/inputs/chat-message?auto_replan=true",
        json={"message": "I only have 15 minutes, suggest a quick meal"},
        headers=headers,
    )
    assert post.status_code == 200
    body = post.json()
    assert body["assistant_message"]
    assert body["recommendation"]["recommendation_id"]

    latest = client.get("/api/v1/inputs/chat-messages/latest?limit=10", headers=headers)
    assert latest.status_code == 200
    events = latest.json()
    assert len(events) >= 2
    assert events[0]["role"] == "assistant"
    assert events[0]["recommendation_id"] == body["recommendation"]["recommendation_id"]
    assert events[1]["role"] == "user"
    assert events[1]["message"] == "I only have 15 minutes, suggest a quick meal"


def test_scope_enforced_for_profile_user_id(client: TestClient, auth_headers) -> None:
    """Authenticated user cannot read another user's profile."""

    alice_headers = auth_headers("journey-scope-alice")
    bob_headers = auth_headers("journey-scope-bob")

    create = client.put(
        "/api/v1/profiles/journey-scope-bob",
        json={"age": 30},
        headers=bob_headers,
    )
    assert create.status_code == 200

    forbidden = client.get("/api/v1/profiles/journey-scope-bob", headers=alice_headers)
    assert forbidden.status_code == 403
