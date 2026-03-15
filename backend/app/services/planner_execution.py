"""Shared planner execution flow for recommendation generation and persistence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.io_contracts import AgentPlanInputV1
from app.agents.rt_workflow import get_railtracks_workflow
from app.agents.tools import decompose_cooking_workflow, schedule_proactive_prep
from app.models.plan_run import PlanRun
from app.models.recommendation import Recommendation
from app.schemas.contracts import (
    CookingDagTask,
    DecisionBlock,
    ExecutionPlanBlock,
    GroceryItem,
    GroceryPlanBlock,
    MealPlanBlock,
    MemoryUpdatesBlock,
    PlanRequest,
    ProactivePrepWindow,
    ReflectionBlock,
    NutritionSummary,
)
from app.services.execution_planning import persist_execution_plan
from app.services.planner import resolve_recipe_metadata_for_title
from app.services.user_memory import (
    count_expiring_items_used,
    infer_used_inventory,
    update_memory_after_recommendation,
)


def _meal_target(target: int | None, *, ratio: float, default: int, minimum: int) -> int:
    if target is None:
        return default
    return max(minimum, int(target * ratio))


def _fallback_recommendation(request: PlanRequest, exc: Exception) -> "AgentPlanOutputV1":
    from app.agents.io_contracts import AgentPlanOutputV1

    inventory_items = request.inventory.items if request.inventory else []
    prioritized = sorted(
        inventory_items,
        key=lambda item: item.expires_in_days if item.expires_in_days is not None else 999,
    )
    primary = prioritized[0].ingredient if prioritized else "balanced ingredients"
    recipe_title = f"{primary.title()} Rescue Bowl" if prioritized else "Balanced Nourish Bowl"

    spoilage_alerts = [
        f"Use {item.ingredient} within {item.expires_in_days} day(s)"
        for item in prioritized
        if item.expires_in_days is not None and item.expires_in_days <= 2
    ][:3]

    substitution_hints = ["Adjust seasoning and portion size to your preference"]
    restrictions = {item.lower() for item in request.constraints.dietary_restrictions}
    if restrictions:
        substitution_hints.append(
            "Respect dietary restrictions: " + ", ".join(sorted(restrictions))
        )
    if request.constraints.allergies:
        substitution_hints.append(
            "Avoid allergens: " + ", ".join(sorted({item.lower() for item in request.constraints.allergies}))
        )

    in_stock = {item.ingredient.lower() for item in inventory_items}
    grocery_seed = ["onion", "garlic", "olive oil", "herbs"]
    grocery_items = [
        GroceryItem(ingredient=item, reason="fallback pantry completion")
        for item in grocery_seed
        if item not in in_stock
    ][:4]

    return AgentPlanOutputV1(
        decision=DecisionBlock(
            recipe_title=recipe_title,
            rationale="Fallback planner generated a stable recommendation for demo continuity",
            confidence=0.62,
        ),
        meal_plan=MealPlanBlock(
            steps=[
                f"Prepare {primary} and other available ingredients",
                "Saute aromatics and add protein/vegetables",
                "Simmer briefly and adjust seasoning",
                "Plate and serve with optional whole grains",
            ],
            nutrition_summary=NutritionSummary(
                calories=_meal_target(
                    request.constraints.calories_target,
                    ratio=0.35,
                    default=560,
                    minimum=320,
                ),
                protein_g=_meal_target(
                    request.constraints.protein_g_target,
                    ratio=0.35,
                    default=28,
                    minimum=12,
                ),
                carbs_g=_meal_target(
                    request.constraints.carbs_g_target,
                    ratio=0.35,
                    default=52,
                    minimum=16,
                ),
                fat_g=_meal_target(
                    request.constraints.fat_g_target,
                    ratio=0.35,
                    default=18,
                    minimum=8,
                ),
            ),
            substitutions=substitution_hints,
            spoilage_alerts=spoilage_alerts,
        ),
        grocery_plan=GroceryPlanBlock(
            missing_ingredients=grocery_items,
            optimized_grocery_list=grocery_items,
            estimated_gap_cost=float(len(grocery_items) * 2.0),
        ),
        execution_plan=ExecutionPlanBlock(),
        reflection=ReflectionBlock(
            status="fallback",
            attempts=1,
            violations=[{"type": "workflow_unavailable", "detail": str(exc)}],
            adjustments=["Used deterministic local fallback planner"],
        ),
        memory_updates=MemoryUpdatesBlock(
            short_term_updates=["fallback_planner_used"],
            long_term_metric_deltas={},
        ),
        trace_notes=[
            "workflow:fallback-local",
            f"fallback:{exc.__class__.__name__}",
        ],
        mode="fallback-local",
    )


async def execute_plan_request(
    *,
    db: Session,
    request: PlanRequest,
    trigger: str,
) -> Recommendation:
    """Run Railtracks planner workflow and persist Recommendation + PlanRun."""

    run = PlanRun(
        user_id=request.user_id,
        status="PROCESSING",
        mode="railtracks-agentic",
        request_payload=request.model_dump(),
        trace_notes=[f"trigger:{trigger}"],
    )
    db.add(run)
    db.flush()

    try:
        workflow = get_railtracks_workflow()
        agent_input = AgentPlanInputV1.from_plan_request(request)
        try:
            recommendation = await workflow.recommend_async(agent_input)
        except Exception as exc:
            recommendation = _fallback_recommendation(request, exc)

        resolved_recipe_metadata = resolve_recipe_metadata_for_title(
            recommendation.decision.recipe_title,
            request.inventory,
            request.constraints,
        )

        rec = Recommendation(
            user_id=request.user_id,
            recipe_title=recommendation.decision.recipe_title,
            steps=recommendation.meal_plan.steps,
            nutrition_summary=recommendation.meal_plan.nutrition_summary.model_dump(),
            substitutions=recommendation.meal_plan.substitutions,
            spoilage_alerts=recommendation.meal_plan.spoilage_alerts,
            grocery_gap=[item.model_dump() for item in recommendation.grocery_plan.optimized_grocery_list],
            recipe_metadata={
                "source": "railtracks-agentic",
                "recipe_title": recommendation.decision.recipe_title,
                "recipe_id": resolved_recipe_metadata.get("recipe_id"),
                "category": resolved_recipe_metadata.get("category"),
                "area": resolved_recipe_metadata.get("area"),
                "tags": resolved_recipe_metadata.get("tags") or [],
                "thumbnail_url": resolved_recipe_metadata.get("thumbnail_url"),
                "youtube_url": resolved_recipe_metadata.get("youtube_url"),
                "source_url": resolved_recipe_metadata.get("source_url"),
                "ingredient_details": resolved_recipe_metadata.get("ingredient_details") or [],
                "api_source": resolved_recipe_metadata.get("api_source") or "railtracks",
                "decision_rationale": recommendation.decision.rationale,
                "confidence": recommendation.decision.confidence,
            },
        )
        db.add(rec)
        db.flush()

        # Default auto-triggered execution tools (local persistence).
        dag_tasks_payload = decompose_cooking_workflow(recipe_id=rec.id, steps=recommendation.meal_plan.steps)
        prep_windows_payload = schedule_proactive_prep(
            task_list=dag_tasks_payload,
            user_availability={"anchor_iso": datetime.now(timezone.utc).isoformat()},
        )
        execution_plan = persist_execution_plan(
            db=db,
            user_id=request.user_id,
            recommendation_id=rec.id,
            recipe_title=recommendation.decision.recipe_title,
            tasks=[CookingDagTask.model_validate(item) for item in dag_tasks_payload],
            prep_windows=[ProactivePrepWindow.model_validate(item) for item in prep_windows_payload],
        )
        execution_payload = execution_plan.model_dump(mode="json")
        recommendation.execution_plan = ExecutionPlanBlock.model_validate(execution_payload)

        used_inventory = infer_used_inventory(
            request.inventory,
            recommendation.meal_plan.steps,
            recommendation.decision.recipe_title,
        )
        expiring_items_used = count_expiring_items_used(request.inventory, used_inventory)
        long_term_delta = update_memory_after_recommendation(
            db=db,
            user_id=request.user_id,
            recipe_title=recommendation.decision.recipe_title,
            used_inventory=used_inventory,
            grocery_gap=[item.ingredient for item in recommendation.grocery_plan.optimized_grocery_list],
            spoilage_alerts_count=len(recommendation.meal_plan.spoilage_alerts),
            expiring_items_used=expiring_items_used,
        )
        recommendation.memory_updates.long_term_metric_deltas = long_term_delta

        bundle_v1 = recommendation.to_recommendation_bundle(rec.id)
        recipe_metadata = dict(rec.recipe_metadata or {})
        recipe_metadata["execution_plan"] = recommendation.execution_plan.model_dump(mode="json")
        recipe_metadata["reflection"] = recommendation.reflection.model_dump(mode="json")
        recipe_metadata["memory_updates"] = recommendation.memory_updates.model_dump(mode="json")
        recipe_metadata["bundle_v1"] = bundle_v1.model_dump(mode="json")
        rec.recipe_metadata = recipe_metadata
        db.add(rec)

        run.status = "COMPLETED"
        run.mode = recommendation.mode
        run.recommendation_id = rec.id
        run.response_payload = bundle_v1.model_dump(mode="json")
        run.trace_notes = run.trace_notes + recommendation.trace_notes
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)

        db.commit()
        db.refresh(rec)
        return rec
    except Exception as exc:
        db.rollback()
        failed_run = db.get(PlanRun, run.id)
        if failed_run:
            failed_run.status = "FAILED"
            failed_run.trace_notes = failed_run.trace_notes + [f"planner_exception:{exc.__class__.__name__}"]
            failed_run.completed_at = datetime.now(timezone.utc)
            db.add(failed_run)
            db.commit()
        raise
