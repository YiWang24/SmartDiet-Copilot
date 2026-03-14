"""Planning endpoints for recommendation generation and retrieval."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.workflow import get_agent_workflow
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.plan_run import PlanRun
from app.models.recommendation import Recommendation
from app.schemas.auth import AuthContext
from app.schemas.contracts import PlanRequest, RecommendationBundle
from app.services.planner import extract_recipe_metadata, retrieve_recipe_candidate
from app.services.planner_context import build_effective_plan_request
from app.services.user_context import ensure_user

router = APIRouter(prefix="/planner", tags=["planner"])


def _to_bundle(rec: Recommendation) -> RecommendationBundle:
    return RecommendationBundle(
        recommendation_id=rec.id,
        recipe_title=rec.recipe_title,
        steps=rec.steps or [],
        nutrition_summary=rec.nutrition_summary,
        substitutions=rec.substitutions or [],
        spoilage_alerts=rec.spoilage_alerts or [],
        grocery_gap=rec.grocery_gap or [],
    )


@router.post("/recommendations", response_model=RecommendationBundle)
async def create_recommendation(
    request: PlanRequest,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationBundle:
    ensure_user(db, current_user)
    if request.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden user scope")

    effective_request = build_effective_plan_request(db, request, current_user.user_id)

    run = PlanRun(
        user_id=current_user.user_id,
        status="PROCESSING",
        mode="pending",
        request_payload=effective_request.model_dump(),
        trace_notes=[],
    )
    db.add(run)
    db.flush()

    workflow = get_agent_workflow()

    try:
        recommendation, trace_notes, mode = workflow.recommend(effective_request)
        selected_recipe = retrieve_recipe_candidate(effective_request.inventory)
        recipe_metadata = extract_recipe_metadata(selected_recipe)

        rec = Recommendation(
            user_id=current_user.user_id,
            recipe_title=recommendation.recipe_title,
            steps=recommendation.steps,
            nutrition_summary=recommendation.nutrition_summary.model_dump(),
            substitutions=recommendation.substitutions,
            spoilage_alerts=recommendation.spoilage_alerts,
            grocery_gap=[item.model_dump() for item in recommendation.grocery_gap],
            recipe_metadata=recipe_metadata,
        )
        db.add(rec)
        db.flush()

        run.status = "COMPLETED"
        run.mode = mode
        run.recommendation_id = rec.id
        run.response_payload = recommendation.model_dump()
        run.trace_notes = trace_notes
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)

        db.commit()
        db.refresh(rec)
        return _to_bundle(rec)
    except Exception:
        run.status = "FAILED"
        run.mode = "error"
        run.trace_notes = ["planner_exception"]
        run.completed_at = datetime.now(timezone.utc)
        db.add(run)
        db.commit()
        raise


@router.post("/recommendations/{recommendation_id}/replan", response_model=RecommendationBundle)
async def replan_recommendation(
        recommendation_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationBundle:
    original = db.get(Recommendation, recommendation_id)
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    if original.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden recommendation scope")

        replanned = Recommendation(
            user_id=current_user.user_id,
            recipe_title=f"{original.recipe_title} (Replan)",
            steps=original.steps,
            nutrition_summary=original.nutrition_summary,
            substitutions=original.substitutions,
            spoilage_alerts=original.spoilage_alerts,
            grocery_gap=original.grocery_gap,
            recipe_metadata=original.recipe_metadata,
        )
    db.add(replanned)
    db.commit()
    db.refresh(replanned)
    return _to_bundle(replanned)


@router.get("/recommendations/latest/{user_id}", response_model=RecommendationBundle)
async def get_latest_recommendation(
    user_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecommendationBundle:
    if user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden user scope")

    latest = db.execute(
        select(Recommendation).where(Recommendation.user_id == user_id).order_by(Recommendation.created_at.desc())
    ).scalars().first()
    if not latest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recommendation found")
    return _to_bundle(latest)


@router.get("/runs/latest/{user_id}")
async def get_latest_plan_run(
    user_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden user scope")

    run = db.execute(select(PlanRun).where(PlanRun.user_id == user_id).order_by(PlanRun.created_at.desc())).scalars().first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No plan run found")

    return {
        "run_id": run.id,
        "status": run.status,
        "mode": run.mode,
        "trace_notes": run.trace_notes,
        "recommendation_id": run.recommendation_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }


@router.get("/recommendations/{recommendation_id}/recipe")
async def get_recipe_detail(
    recommendation_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rec = db.get(Recommendation, recommendation_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    if rec.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden recommendation scope")
    return {
        "recommendation_id": rec.id,
        "recipe_title": rec.recipe_title,
        "steps": rec.steps,
        "recipe_metadata": rec.recipe_metadata or {},
    }


@router.get("/recommendations/{recommendation_id}/nutrition")
async def get_nutrition_summary(
    recommendation_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    rec = db.get(Recommendation, recommendation_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    if rec.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden recommendation scope")
    return rec.nutrition_summary


@router.get("/recommendations/{recommendation_id}/grocery-gap")
async def get_grocery_gap(
    recommendation_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    rec = db.get(Recommendation, recommendation_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    if rec.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden recommendation scope")
    return rec.grocery_gap or []
