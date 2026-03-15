"""Tool functions exposed to Railtracks planner agent."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.agents.rt_config import RAILTRACKS_AVAILABLE, rt
from app.core.database import SessionLocal
from app.schemas.contracts import (
    ConstraintSet,
    CookingDagTask,
    InventorySnapshot,
    ProactivePrepWindow,
)
from app.services.gemini_vision import (
    parse_fridge_ingredients_with_gemini,
    parse_meal_with_gemini,
    parse_receipt_with_gemini,
)
from app.services.execution_planning import (
    build_cooking_dag_tasks,
    build_proactive_prep_windows,
    persist_execution_plan,
)
from app.services.planner import (
    calculate_nutrition,
    generate_grocery_gap,
    retrieve_recipe_candidate,
    retrieve_recipe_candidates as retrieve_recipe_candidates_service,
)

# Create a no-op decorator for when Railtracks is not available
def _noop_decorator(func: Callable[..., Any]) -> Callable[..., Any]:
    """No-op decorator that returns the function unchanged."""
    return func

# Use the Railtracks decorator if available, otherwise use no-op
_function_node = rt.function_node if RAILTRACKS_AVAILABLE and rt else _noop_decorator


@_function_node
def analyze_fridge_vision(image_url: str, detected_items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize fridge scan signals into ingredient inventory."""

    if detected_items:
        return {"image_url": image_url, "ingredients": detected_items}

    parsed_items = parse_fridge_ingredients_with_gemini(image_url)
    return {"image_url": image_url, "ingredients": parsed_items}


@_function_node
def analyze_meal_vision(
    image_url: str,
    meal_name: str | None = None,
    calories: int | None = None,
    protein_g: int | None = None,
    carbs_g: int | None = None,
    fat_g: int | None = None,
) -> dict[str, Any]:
    """Return normalized meal recognition and nutrition estimate."""

    parsed = parse_meal_with_gemini(image_url) if not any([meal_name, calories, protein_g, carbs_g, fat_g]) else {}
    if not any([meal_name, calories, protein_g, carbs_g, fat_g]) and not parsed:
        raise ValueError("Meal vision parsing failed")

    return {
        "image_url": image_url,
        "meal_name": meal_name or (parsed or {}).get("meal_name") or "recognized meal",
        "calories": calories or (parsed or {}).get("calories") or 0,
        "protein_g": protein_g or (parsed or {}).get("protein_g") or 0,
        "carbs_g": carbs_g or (parsed or {}).get("carbs_g") or 0,
        "fat_g": fat_g or (parsed or {}).get("fat_g") or 0,
        "highlights": (parsed or {}).get("highlights") or [],
        "suggestions": (parsed or {}).get("suggestions") or [],
    }


@_function_node
def parse_receipt_items(image_url: str, items: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Normalize receipt extraction payload."""

    if items:
        return {"image_url": image_url, "items": items}

    parsed_items = parse_receipt_with_gemini(image_url)
    return {"image_url": image_url, "items": parsed_items}


@_function_node
def retrieve_recipe_candidates(
    inventory: dict[str, Any] | None = None,
    constraints: dict[str, Any] | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Get recipe candidates from TheMealDB and return selected + ranked list."""

    snapshot = None
    if inventory:
        snapshot = InventorySnapshot.model_validate(inventory)

    constraint_obj = None
    if constraints:
        constraint_obj = ConstraintSet.model_validate(constraints)

    candidates = retrieve_recipe_candidates_service(snapshot, constraints=constraint_obj, limit=limit)
    selected = candidates[0] if candidates else retrieve_recipe_candidate(snapshot, constraints=constraint_obj)
    return {"selected": selected, "candidates": candidates}


@_function_node
def calculate_meal_macros(recipe: dict[str, Any], inventory: dict[str, Any] | None = None) -> dict[str, Any]:
    """Estimate meal macros for candidate recipe."""

    snapshot = None
    if inventory:
        snapshot = InventorySnapshot.model_validate(inventory)
    return calculate_nutrition(recipe, snapshot).model_dump()


@_function_node
def generate_grocery_gap_tool(recipe: dict[str, Any], inventory: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Create minimal shopping list from recipe and inventory difference."""

    snapshot = None
    if inventory:
        snapshot = InventorySnapshot.model_validate(inventory)
    return generate_grocery_gap(recipe, snapshot)


@_function_node
def decompose_cooking_workflow(
    recipe_id: str | None = None,
    steps: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Decompose recipe steps into DAG tasks."""

    _ = recipe_id
    tasks = build_cooking_dag_tasks(steps or [])
    return [task.model_dump() for task in tasks]


@_function_node
def schedule_proactive_prep(
    task_list: list[dict[str, Any]],
    user_availability: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Allocate short proactive prep windows for DAG tasks."""

    anchor = None
    if user_availability and user_availability.get("anchor_iso"):
        try:
            anchor = datetime.fromisoformat(user_availability["anchor_iso"])
        except Exception:
            anchor = None
    tasks = [CookingDagTask.model_validate(item) for item in task_list]
    windows = build_proactive_prep_windows(tasks, anchor=anchor or datetime.now(timezone.utc))
    return [window.model_dump() for window in windows]


@_function_node
def sync_to_calendar(
    user_id: str,
    recommendation_id: str,
    recipe_title: str,
    cooking_dag_tasks: list[dict[str, Any]] | None = None,
    proactive_prep_windows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist calendar, DAG tasks, and prep windows locally."""

    tasks = [CookingDagTask.model_validate(item) for item in (cooking_dag_tasks or [])]
    windows = [ProactivePrepWindow.model_validate(item) for item in (proactive_prep_windows or [])]

    db = SessionLocal()
    try:
        execution = persist_execution_plan(
            db=db,
            user_id=user_id,
            recommendation_id=recommendation_id,
            recipe_title=recipe_title,
            tasks=tasks,
            prep_windows=windows,
        )
        db.commit()
        return execution.model_dump()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
