"""Tests for TheMealDB retrieval and field parsing."""

from __future__ import annotations

from app.schemas.contracts import InventoryItem, InventorySnapshot
from app.services import planner


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_parse_meal_detail_extracts_required_fields() -> None:
    meal = {
        "idMeal": "52772",
        "strMeal": "Teriyaki Chicken Casserole",
        "strCategory": "Chicken",
        "strArea": "Japanese",
        "strInstructions": "Step one. Step two.",
        "strMealThumb": "https://www.themealdb.com/images/media/meals/wvpsxx1468256321.jpg",
        "strYoutube": "https://www.youtube.com/watch?v=4aZr5hZXP_s",
        "strSource": "https://damndelicious.net/2016/05/19/teriyaki-chicken-casserole/",
        "strIngredient1": "soy sauce",
        "strMeasure1": "3/4 cup",
        "strIngredient2": "chicken breast",
        "strMeasure2": "500g",
        "strIngredient3": "",
        "strMeasure3": "",
        "strTags": "Meat,Casserole",
    }

    parsed = planner._parse_meal_detail(meal)

    assert parsed["recipe_id"] == "52772"
    assert parsed["recipe_title"] == "Teriyaki Chicken Casserole"
    assert parsed["category"] == "Chicken"
    assert parsed["area"] == "Japanese"
    assert parsed["thumbnail_url"].startswith("https://")
    assert parsed["youtube_url"].startswith("https://")
    assert parsed["source_url"].startswith("https://")
    assert parsed["tags"] == ["Meat", "Casserole"]
    assert parsed["ingredient_details"][0]["ingredient"] == "soy sauce"
    assert parsed["ingredient_details"][0]["measure"] == "3/4 cup"


def test_retrieve_recipe_candidates_prefers_multi_match_ids(monkeypatch) -> None:
    planner.settings.recipe_api_base_url = "https://www.themealdb.com/api/json/v1/1"

    def fake_get(url: str, params: dict | None = None, timeout: float = 5.0):  # noqa: ARG001
        if url.endswith("/filter.php"):
            ingredient = params["i"]
            if ingredient == "spinach":
                return _FakeResponse({"meals": [{"idMeal": "1001"}, {"idMeal": "1002"}]})
            if ingredient == "tofu":
                return _FakeResponse({"meals": [{"idMeal": "1001"}, {"idMeal": "1003"}]})
            return _FakeResponse({"meals": []})

        if url.endswith("/lookup.php"):
            meal_id = params["i"]
            return _FakeResponse(
                {
                    "meals": [
                        {
                            "idMeal": meal_id,
                            "strMeal": f"Meal {meal_id}",
                            "strCategory": "Vegan",
                            "strArea": "Global",
                            "strInstructions": "Cook. Serve.",
                            "strMealThumb": f"https://img/{meal_id}.jpg",
                            "strYoutube": "https://youtube/test",
                            "strSource": "https://source/test",
                            "strIngredient1": "tofu",
                            "strMeasure1": "200g",
                        }
                    ]
                }
            )

        raise AssertionError(f"Unexpected URL: {url}")

    monkeypatch.setattr(planner.httpx, "get", fake_get)

    inventory = InventorySnapshot(
        user_id="u1",
        items=[
            InventoryItem(ingredient="spinach", quantity="1 bunch", expires_in_days=1),
            InventoryItem(ingredient="tofu", quantity="200g", expires_in_days=2),
        ],
    )

    candidates = planner.retrieve_recipe_candidates(inventory, limit=3)

    assert len(candidates) >= 1
    assert candidates[0]["recipe_id"] == "1001"
    assert candidates[0]["ingredient_details"][0]["ingredient"] == "tofu"


def test_retrieve_recipe_candidate_falls_back_on_api_errors(monkeypatch) -> None:
    planner.settings.recipe_api_base_url = "https://www.themealdb.com/api/json/v1/1"

    def failing_get(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("network error")

    monkeypatch.setattr(planner.httpx, "get", failing_get)

    inventory = InventorySnapshot(
        user_id="u1",
        items=[InventoryItem(ingredient="spinach", quantity="1 bunch", expires_in_days=1)],
    )

    recipe = planner.retrieve_recipe_candidate(inventory)

    assert recipe["recipe_title"].startswith("Quick")
    assert recipe["ingredient_details"]
