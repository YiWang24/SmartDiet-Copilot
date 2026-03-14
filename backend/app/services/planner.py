"""Planner service utilities for recommendation generation."""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.contracts import InventorySnapshot, NutritionSummary

settings = get_settings()


def _normalize_ingredient_query(ingredient: str) -> str:
    return ingredient.strip().lower().replace(" ", "_")


def _split_steps(instructions: str) -> list[str]:
    if not instructions:
        return ["Follow recipe preparation steps", "Cook until done", "Serve"]

    lines = [line.strip() for line in re.split(r"[\r\n]+", instructions) if line.strip()]
    if len(lines) <= 1:
        sentence_parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", instructions) if part.strip()]
        lines = sentence_parts or lines

    return lines[:8] if lines else ["Follow recipe preparation steps", "Cook until done", "Serve"]


def _extract_ingredient_details(meal: dict[str, Any]) -> list[dict[str, str | None]]:
    details: list[dict[str, str | None]] = []
    for idx in range(1, 21):
        ingredient = (meal.get(f"strIngredient{idx}") or "").strip()
        measure = (meal.get(f"strMeasure{idx}") or "").strip()
        if ingredient:
            details.append({"ingredient": ingredient.lower(), "measure": measure or None})
    return details


def _parse_meal_detail(meal: dict[str, Any]) -> dict[str, Any]:
    ingredient_details = _extract_ingredient_details(meal)
    tags_raw = meal.get("strTags") or ""
    tags = [tag.strip() for tag in tags_raw.split(",") if tag.strip()]

    parsed = {
        "recipe_id": meal.get("idMeal") or "",
        "recipe_title": meal.get("strMeal") or "Suggested Meal",
        "category": meal.get("strCategory") or None,
        "area": meal.get("strArea") or None,
        "instructions": meal.get("strInstructions") or "",
        "steps": _split_steps(meal.get("strInstructions") or ""),
        "ingredients": [item["ingredient"] for item in ingredient_details],
        "ingredient_details": ingredient_details,
        "tags": tags,
        "thumbnail_url": meal.get("strMealThumb") or None,
        "youtube_url": meal.get("strYoutube") or None,
        "source_url": meal.get("strSource") or None,
        "api_source": "themealdb",
        "substitutions": ["Swap protein source based on dietary preference"],
    }
    return parsed


def _fallback_recipe(inventory: InventorySnapshot | None) -> dict[str, Any]:
    first = inventory.items[0].ingredient if inventory and inventory.items else "vegetables"
    details = [{"ingredient": item.ingredient.lower(), "measure": item.quantity} for item in (inventory.items or [])]
    if not details:
        details = [{"ingredient": first.lower(), "measure": None}]

    return {
        "recipe_id": "fallback-local",
        "recipe_title": f"Quick {first.title()} Bowl",
        "category": "Quick Meal",
        "area": "Universal",
        "instructions": "Prepare ingredients, stir-fry quickly, and serve.",
        "steps": [
            f"Prepare {first} and remaining available ingredients",
            "Stir-fry with light seasoning for 8-10 minutes",
            "Serve immediately",
        ],
        "ingredients": [item["ingredient"] for item in details],
        "ingredient_details": details,
        "tags": ["fallback", "quick"],
        "thumbnail_url": None,
        "youtube_url": None,
        "source_url": None,
        "api_source": "fallback",
        "substitutions": ["Use tofu or beans for extra protein"],
    }


def _request_json(endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.recipe_api_base_url:
        return None

    url = f"{settings.recipe_api_base_url}/{endpoint}"
    response = httpx.get(url, params=params, timeout=5.0)
    response.raise_for_status()
    return response.json()


def _fetch_lookup_meal(meal_id: str) -> dict[str, Any] | None:
    payload = _request_json("lookup.php", {"i": meal_id})
    if not payload:
        return None
    meals = payload.get("meals") or []
    return meals[0] if meals else None


def retrieve_recipe_candidates(inventory: InventorySnapshot | None, limit: int = 5) -> list[dict[str, Any]]:
    """Retrieve ordered recipe candidates from TheMealDB free API endpoints."""

    if not settings.recipe_api_base_url:
        return []

    prioritized = []
    if inventory and inventory.items:
        prioritized = sorted(
            [item for item in inventory.items if item.ingredient],
            key=lambda x: x.expires_in_days if x.expires_in_days is not None else 999,
        )

    try:
        score_by_id: dict[str, int] = {}
        ingredient_queries = prioritized[:3] if prioritized else []

        for item in ingredient_queries:
            payload = _request_json("filter.php", {"i": _normalize_ingredient_query(item.ingredient)})
            meals = (payload or {}).get("meals") or []
            for meal in meals:
                meal_id = meal.get("idMeal")
                if meal_id:
                    score_by_id[meal_id] = score_by_id.get(meal_id, 0) + 1

        ranked_ids = [meal_id for meal_id, _ in sorted(score_by_id.items(), key=lambda pair: pair[1], reverse=True)]

        parsed: list[dict[str, Any]] = []
        for meal_id in ranked_ids:
            meal = _fetch_lookup_meal(meal_id)
            if meal:
                parsed.append(_parse_meal_detail(meal))
            if len(parsed) >= limit:
                break

        if parsed:
            return parsed

        if prioritized:
            payload = _request_json("search.php", {"s": prioritized[0].ingredient})
            meals = (payload or {}).get("meals") or []
            if meals:
                return [_parse_meal_detail(meals[0])]

        payload = _request_json("random.php", {})
        meals = (payload or {}).get("meals") or []
        if meals:
            return [_parse_meal_detail(meals[0])]

        return []
    except Exception:
        return []


def retrieve_recipe_candidate(inventory: InventorySnapshot | None) -> dict[str, Any]:
    """Retrieve one recipe candidate with robust fallback."""

    candidates = retrieve_recipe_candidates(inventory, limit=1)
    if candidates:
        return candidates[0]
    return _fallback_recipe(inventory)


def calculate_nutrition(recipe: dict[str, Any], inventory: InventorySnapshot | None) -> NutritionSummary:
    """Heuristic nutrition estimate for MVP."""

    ingredient_count = max(1, len(recipe.get("ingredients") or []))
    inventory_bonus = len(inventory.items) if inventory else 0
    calories = 320 + ingredient_count * 35 + inventory_bonus * 20
    protein = 18 + ingredient_count * 3
    carbs = 28 + ingredient_count * 4
    fat = 10 + ingredient_count * 2
    return NutritionSummary(calories=calories, protein_g=protein, carbs_g=carbs, fat_g=fat)


def generate_grocery_gap(recipe: dict[str, Any], inventory: InventorySnapshot | None) -> list[dict[str, str]]:
    """Create minimal grocery gap between recipe and current inventory."""

    in_stock = {item.ingredient.lower() for item in (inventory.items if inventory else [])}
    gap: list[dict[str, str]] = []
    for ingredient in recipe.get("ingredients") or []:
        normalized = ingredient.lower()
        if normalized not in in_stock:
            gap.append({"ingredient": normalized, "reason": "required by selected recipe"})
    return gap[:6]


def extract_recipe_metadata(recipe: dict[str, Any]) -> dict[str, Any]:
    """Extract normalized metadata fields for persistence and API detail view."""

    return {
        "recipe_id": recipe.get("recipe_id"),
        "category": recipe.get("category"),
        "area": recipe.get("area"),
        "tags": recipe.get("tags") or [],
        "thumbnail_url": recipe.get("thumbnail_url"),
        "youtube_url": recipe.get("youtube_url"),
        "source_url": recipe.get("source_url"),
        "ingredient_details": recipe.get("ingredient_details") or [],
        "api_source": recipe.get("api_source") or "unknown",
    }
