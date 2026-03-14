"""Planner context assembly service combining request and persisted memory."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat_message import ChatMessage
from app.models.goal import Goal
from app.models.meal_log import MealLog
from app.models.pantry_item import PantryItem
from app.schemas.contracts import ConstraintSet, InventoryItem, InventorySnapshot, MealLog as MealLogSchema, PlanRequest


def _is_constraints_empty(constraints: ConstraintSet) -> bool:
    return (
        constraints.calories_target is None
        and constraints.protein_g_target is None
        and constraints.carbs_g_target is None
        and constraints.fat_g_target is None
        and not constraints.dietary_restrictions
        and not constraints.allergies
        and constraints.budget_limit is None
        and constraints.max_cook_time_minutes is None
    )


def _load_goal_constraints(db: Session, user_id: str) -> ConstraintSet | None:
    goal = db.get(Goal, user_id)
    if not goal:
        return None
    return ConstraintSet(
        calories_target=goal.calories_target,
        protein_g_target=goal.protein_g_target,
        carbs_g_target=goal.carbs_g_target,
        fat_g_target=goal.fat_g_target,
        dietary_restrictions=goal.dietary_restrictions or [],
        allergies=goal.allergies or [],
        budget_limit=goal.budget_limit,
        max_cook_time_minutes=goal.max_cook_time_minutes,
    )


def _load_inventory_snapshot(db: Session, user_id: str) -> InventorySnapshot | None:
    items = db.execute(select(PantryItem).where(PantryItem.user_id == user_id)).scalars().all()
    if not items:
        return None

    mapped = [
        InventoryItem(
            ingredient=item.ingredient,
            quantity=item.quantity,
            expires_in_days=item.expires_in_days,
        )
        for item in items
    ]
    return InventorySnapshot(user_id=user_id, items=mapped)


def _load_latest_meal(db: Session, user_id: str) -> MealLogSchema | None:
    meal = (
        db.execute(select(MealLog).where(MealLog.user_id == user_id).order_by(MealLog.created_at.desc()))
        .scalars()
        .first()
    )
    if not meal:
        return None

    return MealLogSchema(
        user_id=user_id,
        meal_name=meal.meal_name,
        calories=meal.calories,
        protein_g=meal.protein_g,
        carbs_g=meal.carbs_g,
        fat_g=meal.fat_g,
    )


def _load_latest_chat_message(db: Session, user_id: str) -> str | None:
    message = (
        db.execute(select(ChatMessage).where(ChatMessage.user_id == user_id).order_by(ChatMessage.created_at.desc()))
        .scalars()
        .first()
    )
    return message.message if message else None


def build_effective_plan_request(db: Session, request: PlanRequest, user_id: str) -> PlanRequest:
    """Merge incoming request with persisted user context."""

    constraints = request.constraints
    if _is_constraints_empty(constraints):
        persisted = _load_goal_constraints(db, user_id)
        if persisted:
            constraints = persisted

    inventory = request.inventory
    if not inventory or not inventory.items:
        inventory = _load_inventory_snapshot(db, user_id)

    latest_meal = request.latest_meal_log or _load_latest_meal(db, user_id)
    user_message = request.user_message or _load_latest_chat_message(db, user_id)

    return PlanRequest(
        user_id=user_id,
        constraints=constraints,
        inventory=inventory,
        latest_meal_log=latest_meal,
        user_message=user_message,
    )
