"""Tool functions exposed to Google ADK planner agent."""

from __future__ import annotations

from typing import Any

from app.schemas.contracts import InventorySnapshot
from app.services.planner import (
    calculate_nutrition,
    generate_grocery_gap,
    retrieve_recipe_candidate,
    retrieve_recipe_candidates as retrieve_recipe_candidates_service,
)


def analyze_fridge_vision(image_url: str, detected_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize fridge scan signals into ingredient inventory."""

    items = detected_items or [
        {"ingredient": "spinach", "quantity": "1 bunch", "expires_in_days": 1},
        {"ingredient": "tofu", "quantity": "400g", "expires_in_days": 2},
    ]
    return {"image_url": image_url, "ingredients": items}


def analyze_meal_vision(
    image_url: str,
    meal_name: str | None = None,
    calories: int | None = None,
    protein_g: int | None = None,
    carbs_g: int | None = None,
    fat_g: int | None = None,
) -> dict[str, Any]:
    """Return normalized meal recognition and nutrition estimate."""

    return {
        "image_url": image_url,
        "meal_name": meal_name or "recognized meal",
        "calories": calories or 520,
        "protein_g": protein_g or 28,
        "carbs_g": carbs_g or 46,
        "fat_g": fat_g or 20,
    }


def parse_receipt_items(image_url: str, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize receipt extraction payload."""

    parsed = items or [
        {"ingredient": "tomato", "quantity": "4", "expires_in_days": 4},
        {"ingredient": "onion", "quantity": "2", "expires_in_days": 7},
    ]
    return {"image_url": image_url, "items": parsed}


def retrieve_recipe_candidates(inventory: dict[str, Any] | None = None, limit: int = 5) -> dict[str, Any]:
    """Get recipe candidates from TheMealDB and return selected + ranked list."""

    snapshot = None
    if inventory:
        snapshot = InventorySnapshot.model_validate(inventory)
    candidates = retrieve_recipe_candidates_service(snapshot, limit=limit)
    selected = candidates[0] if candidates else retrieve_recipe_candidate(snapshot)
    return {"selected": selected, "candidates": candidates}


def calculate_meal_macros(recipe: dict[str, Any], inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Estimate meal macros for candidate recipe."""

    snapshot = None
    if inventory:
        snapshot = InventorySnapshot.model_validate(inventory)
    return calculate_nutrition(recipe, snapshot).model_dump()


def generate_grocery_gap_tool(recipe: dict[str, Any], inventory: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Create minimal shopping list from recipe and inventory difference."""

    snapshot = None
    if inventory:
        snapshot = InventorySnapshot.model_validate(inventory)
    return generate_grocery_gap(recipe, snapshot)
