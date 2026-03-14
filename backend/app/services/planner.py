"""Planner service utilities for recommendation generation."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.contracts import InventorySnapshot, NutritionSummary

settings = get_settings()


def _fallback_recipe(inventory: InventorySnapshot | None) -> dict[str, Any]:
    first = inventory.items[0].ingredient if inventory and inventory.items else "vegetables"
    return {
        "recipe_title": f"Quick {first.title()} Bowl",
        "steps": [
            f"Prepare {first} and remaining available ingredients",
            "Stir-fry with light seasoning for 8-10 minutes",
            "Serve immediately",
        ],
        "ingredients": [item.ingredient for item in inventory.items] if inventory else [first],
        "substitutions": ["Use tofu or beans for extra protein"],
    }


def retrieve_recipe_candidate(inventory: InventorySnapshot | None) -> dict[str, Any]:
    """Retrieve candidate recipe from TheMealDB, fallback to local template."""

    query = inventory.items[0].ingredient if inventory and inventory.items else "chicken"

    try:
        url = f"{settings.recipe_api_base_url}/search.php"
        response = httpx.get(url, params={"s": query}, timeout=5.0)
        response.raise_for_status()
        meals = response.json().get("meals") or []
        if not meals:
            return _fallback_recipe(inventory)

        meal = meals[0]
        ingredients = []
        for idx in range(1, 21):
            key = f"strIngredient{idx}"
            value = (meal.get(key) or "").strip()
            if value:
                ingredients.append(value.lower())

        instructions = meal.get("strInstructions") or ""
        steps = [line.strip() for line in instructions.splitlines() if line.strip()][:6]
        if not steps:
            steps = ["Follow recipe preparation steps", "Cook until done", "Serve"]

        return {
            "recipe_title": meal.get("strMeal") or "Suggested Meal",
            "steps": steps,
            "ingredients": ingredients,
            "substitutions": ["Swap protein source based on dietary preference"],
        }
    except Exception:
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
