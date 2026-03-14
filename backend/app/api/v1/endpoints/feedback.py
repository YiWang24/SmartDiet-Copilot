"""Feedback endpoints for accept/reject and replan triggers."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.feedback_event import FeedbackEvent
from app.models.recommendation import Recommendation
from app.schemas.auth import AuthContext
from app.schemas.contracts import FeedbackPatch, FeedbackResponse

router = APIRouter(prefix="/feedback", tags=["feedback"])


@router.patch("/recommendations/{recommendation_id}", response_model=FeedbackResponse)
async def patch_recommendation_feedback(
    recommendation_id: str,
    payload: FeedbackPatch,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    rec = db.get(Recommendation, recommendation_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")
    if rec.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden recommendation scope")

    event = FeedbackEvent(
        user_id=current_user.user_id,
        recommendation_id=recommendation_id,
        action=payload.action,
        message=payload.message,
    )
    db.add(event)
    db.flush()

    replanned_id: str | None = None
    if payload.action == "reject":
        replanned = Recommendation(
            user_id=current_user.user_id,
            recipe_title=f"{rec.recipe_title} (Replan)",
            steps=rec.steps,
            nutrition_summary=rec.nutrition_summary,
            substitutions=rec.substitutions,
            spoilage_alerts=rec.spoilage_alerts,
            grocery_gap=rec.grocery_gap,
            recipe_metadata=rec.recipe_metadata,
        )
        db.add(replanned)
        db.flush()
        replanned_id = replanned.id

    db.commit()

    return FeedbackResponse(
        event_id=event.id,
        recommendation_id=recommendation_id,
        action=payload.action,
        message=payload.message,
        replanned_recommendation_id=replanned_id,
    )
