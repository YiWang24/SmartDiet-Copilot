"""Planning endpoints for recommendation generation and retrieval."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.recommendation import Recommendation
from app.schemas.auth import AuthContext
from app.schemas.contracts import PlanRequest, RecommendationBundle
from app.services.planner import calculate_nutrition, generate_grocery_gap, retrieve_recipe_candidate
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

    recipe = retrieve_recipe_candidate(request.inventory)
    nutrition = calculate_nutrition(recipe, request.inventory)
    grocery_gap = generate_grocery_gap(recipe, request.inventory)
    spoilage_alerts = []
    if request.inventory:
        spoilage_alerts = [
            f"Use {item.ingredient} soon"
            for item in request.inventory.items
            if item.expires_in_days is not None and item.expires_in_days <= 2
        ]

    rec = Recommendation(
        user_id=current_user.user_id,
        recipe_title=recipe["recipe_title"],
        steps=recipe["steps"],
        nutrition_summary=nutrition.model_dump(),
        substitutions=recipe.get("substitutions") or [],
        spoilage_alerts=spoilage_alerts,
        grocery_gap=grocery_gap,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)

    return _to_bundle(rec)


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
    return {"recommendation_id": rec.id, "recipe_title": rec.recipe_title, "steps": rec.steps}


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
