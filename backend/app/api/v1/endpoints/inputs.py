"""Input ingestion endpoints for fridge, meal, receipt, and chat context."""

from datetime import datetime, time, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.chat_message import ChatMessage
from app.models.chat_turn import ChatTurn
from app.models.input_job import InputJob
from app.models.meal_log import MealLog
from app.models.pantry_item import PantryItem
from app.schemas.auth import AuthContext
from app.schemas.contracts import (
    ChatMessageEvent,
    ChatMessageRequest,
    ChatMessageResponse,
    ConstraintSet,
    DailyNutritionSummary,
    FridgeScanRequest,
    JobEnvelope,
    JobStatus,
    MealScanRequest,
    PantryItemResponse,
    PlanRequest,
    RecommendationBundle,
    ReceiptScanRequest,
)
from app.services.input_jobs import process_input_job
from app.services.planner_context import build_effective_plan_request
from app.services.planner_execution import execute_plan_request
from app.services.recommendation_mapper import recommendation_to_bundle
from app.services.user_context import ensure_user

router = APIRouter(prefix="/inputs", tags=["inputs"])


def _normalize_ingredient_name(value: str | None) -> str:
    return " ".join((value or "").strip().lower().split())


def _dedupe_pantry_items(items: list[PantryItem]) -> list[dict]:
    merged: dict[str, dict] = {}

    for item in items:
        key = _normalize_ingredient_name(item.ingredient)
        if not key:
            continue

        current = merged.get(key)
        if current is None:
            merged[key] = {
                "item_id": item.id,
                "ingredient": key,
                "quantity": item.quantity,
                "expires_in_days": item.expires_in_days,
                "source": item.source,
                "updated_at": item.updated_at,
            }
            continue

        if not current["quantity"] and item.quantity:
            current["quantity"] = item.quantity
        if item.expires_in_days is not None and (
            current["expires_in_days"] is None or item.expires_in_days < current["expires_in_days"]
        ):
            current["expires_in_days"] = item.expires_in_days
        if item.updated_at and item.updated_at > current["updated_at"]:
            current["item_id"] = item.id
            current["source"] = item.source
            current["updated_at"] = item.updated_at

    return sorted(
        merged.values(),
        key=lambda row: (
            row["expires_in_days"] is None,
            row["expires_in_days"] if row["expires_in_days"] is not None else 9999,
            row["ingredient"],
        ),
    )


def _create_input_job(
    *,
    db: Session,
    user_id: str,
    input_type: str,
    payload: dict,
    background_tasks: BackgroundTasks,
) -> JobEnvelope:
    job = InputJob(user_id=user_id, input_type=input_type, status=JobStatus.PENDING.value, payload=payload)
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(process_input_job, job.id)

    return JobEnvelope(job_id=job.id, status=JobStatus.PENDING)


def _format_assistant_message(recommendation: RecommendationBundle | None) -> str:
    if not recommendation:
        return "Message received. Share more constraints and I can generate a full meal plan."

    nutrition = recommendation.meal_plan.nutrition_summary
    return "\n".join(
        [
            f"Recommendation: {recommendation.decision.recipe_title or 'Suggested meal'}",
            recommendation.decision.rationale
            or "Generated based on your latest profile and pantry data.",
            f"Nutrition: {nutrition.calories or 0} kcal • {nutrition.protein_g or 0}g protein",
        ]
    )


@router.post("/fridge-scan", response_model=JobEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def submit_fridge_scan(
    payload: FridgeScanRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobEnvelope:
    ensure_user(db, current_user)
    return _create_input_job(
        db=db,
        user_id=current_user.user_id,
        input_type="fridge_scan",
        payload=payload.model_dump(),
        background_tasks=background_tasks,
    )


@router.post("/meal-scan", response_model=JobEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def submit_meal_scan(
    payload: MealScanRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobEnvelope:
    ensure_user(db, current_user)
    return _create_input_job(
        db=db,
        user_id=current_user.user_id,
        input_type="meal_scan",
        payload=payload.model_dump(),
        background_tasks=background_tasks,
    )


@router.post("/receipt-scan", response_model=JobEnvelope, status_code=status.HTTP_202_ACCEPTED)
async def submit_receipt_scan(
    payload: ReceiptScanRequest,
    background_tasks: BackgroundTasks,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobEnvelope:
    ensure_user(db, current_user)
    return _create_input_job(
        db=db,
        user_id=current_user.user_id,
        input_type="receipt_scan",
        payload=payload.model_dump(),
        background_tasks=background_tasks,
    )


@router.get("/jobs/{job_id}", response_model=JobEnvelope)
async def get_job_status(
    job_id: str,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> JobEnvelope:
    job = db.get(InputJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Input job not found")
    if job.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden job scope")

    return JobEnvelope(job_id=job.id, status=JobStatus(job.status), result=job.result)


@router.get("/pantry", response_model=list[PantryItemResponse])
async def get_pantry(
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PantryItemResponse]:
    items = (
        db.execute(
            select(PantryItem)
            .where(PantryItem.user_id == current_user.user_id)
            .order_by(PantryItem.expires_in_days.asc().nullslast())
        )
        .scalars()
        .all()
    )
    deduped_rows = _dedupe_pantry_items(items)
    return [PantryItemResponse(**row) for row in deduped_rows]


@router.delete("/pantry/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pantry_item(
    item_id: int,
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    item = db.get(PantryItem, item_id)
    if not item or item.user_id != current_user.user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pantry item not found")
    db.delete(item)
    db.commit()


@router.get("/spoilage-alerts")
async def get_spoilage_alerts(
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    items = (
        db.execute(
            select(PantryItem)
            .where(
                PantryItem.user_id == current_user.user_id,
                PantryItem.expires_in_days.isnot(None),
                PantryItem.expires_in_days <= 3,
            )
            .order_by(PantryItem.expires_in_days.asc())
        )
        .scalars()
        .all()
    )
    return [
        {
            "item_id": item.id,
            "ingredient": item.ingredient,
            "expires_in_days": item.expires_in_days,
            "urgency": "critical" if item.expires_in_days <= 1 else "warning",
        }
        for item in items
    ]


@router.post("/chat-message", response_model=ChatMessageResponse)
async def submit_chat_message(
    payload: ChatMessageRequest,
    auto_replan: bool = Query(default=False),
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatMessageResponse:
    ensure_user(db, current_user)

    event = ChatMessage(user_id=current_user.user_id, message=payload.message)
    user_turn = ChatTurn(
        user_id=current_user.user_id,
        role="user",
        message=payload.message,
        recommendation_id=None,
    )
    db.add_all([event, user_turn])
    db.commit()
    db.refresh(event)

    recommendation: RecommendationBundle | None = None
    assistant_message: str | None = None
    if auto_replan:
        base_request = build_effective_plan_request(
            db,
            PlanRequest(
                user_id=current_user.user_id,
                constraints=ConstraintSet(),
                user_message=payload.message,
            ),
            current_user.user_id,
        )
        rec = await execute_plan_request(db=db, request=base_request, trigger="chat_auto_replan")
        recommendation = recommendation_to_bundle(rec)
        assistant_message = _format_assistant_message(recommendation)
        assistant_turn = ChatTurn(
            user_id=current_user.user_id,
            role="assistant",
            message=assistant_message,
            recommendation_id=recommendation.recommendation_id,
        )
        db.add(assistant_turn)
        db.commit()

    return ChatMessageResponse(
        event_id=event.id,
        user_id=event.user_id,
        message=event.message,
        assistant_message=assistant_message,
        recommendation=recommendation,
    )


@router.get("/chat-messages/latest", response_model=list[ChatMessageEvent])
async def get_latest_chat_messages(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ChatMessageEvent]:
    turns = (
        db.execute(
            select(ChatTurn)
            .where(ChatTurn.user_id == current_user.user_id)
            .order_by(ChatTurn.created_at.desc(), ChatTurn.id.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if turns:
        rows = [
            ChatMessageEvent(
                event_id=event.id,
                user_id=event.user_id,
                role="assistant" if event.role == "assistant" else "user",
                source="turn",
                message=event.message,
                created_at=event.created_at,
                recommendation_id=event.recommendation_id,
            )
            for event in turns
        ]
        if len(rows) < limit:
            oldest_turn_at = turns[-1].created_at
            legacy_events = (
                db.execute(
                    select(ChatMessage)
                    .where(
                        ChatMessage.user_id == current_user.user_id,
                        ChatMessage.created_at < oldest_turn_at,
                    )
                    .order_by(ChatMessage.created_at.desc())
                    .limit(limit - len(rows))
                )
                .scalars()
                .all()
            )
            rows.extend(
                [
                    ChatMessageEvent(
                        event_id=event.id,
                        user_id=event.user_id,
                        role="user",
                        source="legacy",
                        message=event.message,
                        created_at=event.created_at,
                        recommendation_id=None,
                    )
                    for event in legacy_events
                ]
            )
        return rows[:limit]

    events = (
        db.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == current_user.user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        ChatMessageEvent(
            event_id=event.id,
            user_id=event.user_id,
            role="user",
            source="legacy",
            message=event.message,
            created_at=event.created_at,
            recommendation_id=None,
        )
        for event in events
    ]


@router.get("/nutrition/today", response_model=DailyNutritionSummary)
async def get_today_nutrition(
    current_user: AuthContext = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyNutritionSummary:
    now_utc = datetime.now(timezone.utc)
    start_of_day = datetime.combine(now_utc.date(), time.min, tzinfo=timezone.utc)

    meals = (
        db.execute(
            select(MealLog)
            .where(
                MealLog.user_id == current_user.user_id,
                MealLog.created_at >= start_of_day,
            )
            .order_by(MealLog.created_at.desc())
        )
        .scalars()
        .all()
    )

    return DailyNutritionSummary(
        calories=sum(int(meal.calories or 0) for meal in meals),
        protein_g=sum(int(meal.protein_g or 0) for meal in meals),
        carbs_g=sum(int(meal.carbs_g or 0) for meal in meals),
        fat_g=sum(int(meal.fat_g or 0) for meal in meals),
        meal_count=len(meals),
    )
