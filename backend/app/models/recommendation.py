"""Recommendation persistence model."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), ForeignKey("users.id", ondelete="CASCADE"), index=True)
    recipe_title: Mapped[str] = mapped_column(String(255))
    steps: Mapped[list[str]] = mapped_column(JSON, default=list)
    nutrition_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    substitutions: Mapped[list[str]] = mapped_column(JSON, default=list)
    spoilage_alerts: Mapped[list[str]] = mapped_column(JSON, default=list)
    grocery_gap: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
