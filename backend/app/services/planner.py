"""Planner service utilities for recommendation generation."""

from __future__ import annotations

import re
from hashlib import md5
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.contracts import ConstraintSet, InventorySnapshot, NutritionSummary

settings = get_settings()

_ANIMAL_INGREDIENT_KEYWORDS = {
    "chicken",
    "beef",
    "pork",
    "lamb",
    "shrimp",
    "fish",
    "salmon",
    "tuna",
    "bacon",
    "meat",
}
_THEMEALDB_INGREDIENT_IMAGE_BASE = "https://www.themealdb.com/images/ingredients"


def _normalize_ingredient_query(ingredient: str) -> str:
    return ingredient.strip().lower().replace(" ", "_")


def _build_endpoint_url(endpoint: str) -> str:
    base = (settings.recipe_api_base_url or "").rstrip("/")
    api_key = (settings.recipe_api_key or "1").strip() or "1"

    if base.endswith("/api.php"):
        return f"https://www.themealdb.com/api/json/v1/{api_key}/{endpoint}"

    if "/api/json/v1/" in base:
        return f"{base}/{endpoint}"

    if base.endswith("/api/json/v1"):
        return f"{base}/{api_key}/{endpoint}"

    return f"{base}/{endpoint}"


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
            normalized = ingredient.lower()
            image_name = normalized.replace(" ", "_")
            details.append(
                {
                    "ingredient": normalized,
                    "measure": measure or None,
                    "thumbnail_url": f"{_THEMEALDB_INGREDIENT_IMAGE_BASE}/{image_name}-small.png",
                }
            )
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


def _request_json(endpoint: str, params: dict[str, Any]) -> dict[str, Any] | None:
    if not settings.recipe_api_base_url:
        return None

    url = _build_endpoint_url(endpoint)
    response = httpx.get(url, params=params, timeout=5.0)
    response.raise_for_status()
    return response.json()


def _fetch_lookup_meal(meal_id: str) -> dict[str, Any] | None:
    payload = _request_json("lookup.php", {"i": meal_id})
    if not payload:
        return None
    meals = payload.get("meals") or []
    return meals[0] if meals else None


def _estimate_cook_minutes(recipe: dict[str, Any]) -> int:
    steps = recipe.get("steps") or []
    ingredients = recipe.get("ingredients") or []
    return max(10, len(steps) * 4 + len(ingredients))


def _violates_restrictions(recipe: dict[str, Any], constraints: ConstraintSet | None) -> bool:
    if not constraints:
        return False

    restrictions = {item.lower() for item in constraints.dietary_restrictions}
    if "vegetarian" not in restrictions and "vegan" not in restrictions:
        return False

    ingredients = {ingredient.lower() for ingredient in (recipe.get("ingredients") or [])}
    for ingredient in ingredients:
        if any(keyword in ingredient for keyword in _ANIMAL_INGREDIENT_KEYWORDS):
            return True
    return False


def _violates_allergies(recipe: dict[str, Any], constraints: ConstraintSet | None) -> bool:
    if not constraints or not constraints.allergies:
        return False
    allergies = {item.lower() for item in constraints.allergies}
    ingredients = {ingredient.lower() for ingredient in (recipe.get("ingredients") or [])}
    return any(allergy in ingredient for allergy in allergies for ingredient in ingredients)


def _score_recipe_candidate(
    recipe: dict[str, Any],
    inventory: InventorySnapshot | None,
    constraints: ConstraintSet | None,
) -> float:
    in_stock = {item.ingredient.lower() for item in (inventory.items if inventory else [])}
    expiring = {
        item.ingredient.lower()
        for item in (inventory.items if inventory else [])
        if item.expires_in_days is not None and item.expires_in_days <= 2
    }

    recipe_ingredients = [ingredient.lower() for ingredient in (recipe.get("ingredients") or [])]
    overlap_count = sum(1 for ingredient in recipe_ingredients if ingredient in in_stock)
    expiring_hits = sum(1 for ingredient in recipe_ingredients if ingredient in expiring)
    grocery_gap = generate_grocery_gap(recipe, inventory)

    nutrition = calculate_nutrition(recipe, inventory)
    score = 0.0

    # Inventory and waste optimization
    score += overlap_count * 3.0
    score += expiring_hits * 2.5
    score -= len(grocery_gap) * 1.5

    # Restriction hard-penalty
    if _violates_restrictions(recipe, constraints):
        score -= 100.0
    if _violates_allergies(recipe, constraints):
        score -= 120.0

    if constraints:
        if constraints.calories_target is not None:
            score -= abs(nutrition.calories - constraints.calories_target) / 140.0
        if constraints.protein_g_target is not None:
            score -= abs(nutrition.protein_g - constraints.protein_g_target) / 20.0
        if constraints.carbs_g_target is not None:
            score -= abs(nutrition.carbs_g - constraints.carbs_g_target) / 30.0
        if constraints.fat_g_target is not None:
            score -= abs(nutrition.fat_g - constraints.fat_g_target) / 20.0

        if constraints.max_cook_time_minutes is not None:
            estimated = _estimate_cook_minutes(recipe)
            if estimated > constraints.max_cook_time_minutes:
                score -= (estimated - constraints.max_cook_time_minutes) * 0.7

        if constraints.budget_limit is not None:
            estimated_gap_cost = len(grocery_gap) * 2.0
            if estimated_gap_cost > constraints.budget_limit:
                score -= (estimated_gap_cost - constraints.budget_limit) * 0.8

    return score


def retrieve_recipe_candidates(
    inventory: InventorySnapshot | None,
    constraints: ConstraintSet | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
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
            ranked = sorted(
                parsed,
                key=lambda recipe: _score_recipe_candidate(recipe, inventory, constraints),
                reverse=True,
            )
            safe_ranked = [
                recipe
                for recipe in ranked
                if not _violates_allergies(recipe, constraints) and not _violates_restrictions(recipe, constraints)
            ]
            if safe_ranked:
                return safe_ranked[:limit]
            return ranked[:limit]

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


def retrieve_recipe_candidate(
    inventory: InventorySnapshot | None,
    constraints: ConstraintSet | None = None,
) -> dict[str, Any]:
    """Retrieve one recipe candidate."""

    candidates = retrieve_recipe_candidates(inventory, constraints=constraints, limit=1)
    if candidates:
        return candidates[0]
    raise RuntimeError("No recipe candidates available from recipe provider")


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


def _normalize_recipe_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()
    return " ".join(normalized.split())


def _recipe_title_similarity(left: str, right: str) -> int:
    if not left or not right:
        return 0
    if left == right:
        return 100
    if left in right or right in left:
        return 80

    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return int((overlap / union) * 100)


def _stable_recipe_index(seed: str, size: int) -> int:
    if size <= 1:
        return 0
    digest = md5(seed.encode("utf-8"), usedforsecurity=False).hexdigest()
    return int(digest, 16) % size


def resolve_recipe_metadata_for_title(
    recipe_title: str | None,
    inventory: InventorySnapshot | None,
    constraints: ConstraintSet | None = None,
) -> dict[str, Any]:
    """Resolve best-effort MealDB metadata for an AI-generated recipe title."""

    normalized_target = _normalize_recipe_title(recipe_title)
    candidates = retrieve_recipe_candidates(inventory, constraints=constraints, limit=8)

    best_candidate = None
    best_score = 0
    if normalized_target:
        for candidate in candidates:
            score = _recipe_title_similarity(
                normalized_target,
                _normalize_recipe_title(candidate.get("recipe_title")),
            )
            if score > best_score:
                best_score = score
                best_candidate = candidate

    if best_candidate and best_score >= 35:
        return extract_recipe_metadata(best_candidate)

    if recipe_title and settings.recipe_api_base_url:
        payload = _request_json("search.php", {"s": recipe_title.strip()})
        meals = (payload or {}).get("meals") or []
        if meals:
            return extract_recipe_metadata(_parse_meal_detail(meals[0]))

    if candidates:
        seed = normalized_target or (recipe_title or "fallback-meal")
        chosen = candidates[_stable_recipe_index(seed, len(candidates))]
        return extract_recipe_metadata(chosen)

    return {}
