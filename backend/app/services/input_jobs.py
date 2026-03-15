"""Background job processor for phase-2 input ingestion."""

from __future__ import annotations

from sqlalchemy import select

from app.agents.tools import analyze_fridge_vision, analyze_meal_vision, parse_receipt_items
from app.core.database import SessionLocal
from app.models.input_job import InputJob
from app.models.meal_log import MealLog
from app.models.pantry_item import PantryItem
from app.models.receipt_event import ReceiptEvent


def _upsert_pantry_item(
    *,
    db,
    user_id: str,
    ingredient: str,
    quantity: str | None,
    expires_in_days: int | None,
    source: str,
) -> None:
    existing = db.execute(
        select(PantryItem).where(PantryItem.user_id == user_id, PantryItem.ingredient == ingredient.lower())
    ).scalar_one_or_none()

    if existing:
        existing.quantity = quantity or existing.quantity
        existing.expires_in_days = expires_in_days if expires_in_days is not None else existing.expires_in_days
        existing.source = source
        db.add(existing)
        return

    db.add(
        PantryItem(
            user_id=user_id,
            ingredient=ingredient.lower(),
            quantity=quantity,
            expires_in_days=expires_in_days,
            source=source,
        )
    )


def process_input_job(job_id: str) -> None:
    """Run ingestion job in background and persist final status/result."""

    db = SessionLocal()
    try:
        job = db.get(InputJob, job_id)
        if not job:
            return

        job.status = "PROCESSING"
        db.add(job)
        db.commit()
        db.refresh(job)

        payload = job.payload or {}
        result: dict = {"input_type": job.input_type}

        if job.input_type == "fridge_scan":
            parsed = analyze_fridge_vision(payload.get("image_url", ""), payload.get("detected_items"))
            items = parsed.get("ingredients") or []
            for item in items:
                _upsert_pantry_item(
                    db=db,
                    user_id=job.user_id,
                    ingredient=item["ingredient"],
                    quantity=item.get("quantity"),
                    expires_in_days=item.get("expires_in_days"),
                    source="fridge_scan",
                )
            result["updated_items"] = len(items)

        elif job.input_type == "meal_scan":
            parsed = analyze_meal_vision(
                payload.get("image_url", ""),
                payload.get("meal_name"),
                payload.get("calories"),
                payload.get("protein_g"),
                payload.get("carbs_g"),
                payload.get("fat_g"),
            )
            meal = MealLog(
                user_id=job.user_id,
                meal_name=parsed.get("meal_name") or "recognized meal",
                calories=parsed.get("calories") or 520,
                protein_g=parsed.get("protein_g") or 28,
                carbs_g=parsed.get("carbs_g") or 46,
                fat_g=parsed.get("fat_g") or 20,
            )
            db.add(meal)
            db.flush()
            result["meal_logged"] = True
            result["meal_log_id"] = meal.id
            result["meal_name"] = meal.meal_name
            result["calories"] = int(meal.calories or 0)
            result["protein_g"] = int(meal.protein_g or 0)
            result["carbs_g"] = int(meal.carbs_g or 0)
            result["fat_g"] = int(meal.fat_g or 0)
            result["highlights"] = parsed.get("highlights") or []
            result["suggestions"] = parsed.get("suggestions") or []

        elif job.input_type == "receipt_scan":
            parsed = parse_receipt_items(payload.get("image_url", ""), payload.get("items"))
            items = parsed.get("items") or []
            receipt = ReceiptEvent(user_id=job.user_id, image_url=payload.get("image_url", ""), parsed_items=items)
            db.add(receipt)
            for item in items:
                _upsert_pantry_item(
                    db=db,
                    user_id=job.user_id,
                    ingredient=item["ingredient"],
                    quantity=item.get("quantity"),
                    expires_in_days=item.get("expires_in_days"),
                    source="receipt_scan",
                )
            result["receipt_event_created"] = True
            result["updated_items"] = len(items)

        else:
            raise ValueError(f"Unsupported input job type: {job.input_type}")

        job.status = "COMPLETED"
        job.result = result
        db.add(job)
        db.commit()
    except Exception as exc:  # pragma: no cover - defensive guard
        db.rollback()
        try:
            failed_job = db.get(InputJob, job_id)
            if failed_job:
                failed_job.status = "FAILED"
                failed_job.error_message = str(exc)
                db.add(failed_job)
                db.commit()
        except Exception:
            db.rollback()
            # Keep this function non-throwing for background execution.
            pass
    finally:
        db.close()
