"""Pydantic schemas for Railtracks workflow input and output."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.contracts import GroceryItem, NutritionSummary


class AgentDraftBundle(BaseModel):
    """Internal flattened draft shape used before V1 bundle assembly."""

    recipe_title: str
    steps: list[str] = Field(default_factory=list)
    nutrition_summary: NutritionSummary
    substitutions: list[str] = Field(default_factory=list)
    spoilage_alerts: list[str] = Field(default_factory=list)
    grocery_gap: list[GroceryItem] = Field(default_factory=list)


class RtGroceryItem(BaseModel):
    """Railtracks grocery item schema."""
    ingredient: str
    reason: str


class RtNutritionSummary(BaseModel):
    """Railtracks nutrition summary schema."""
    calories: int = 0
    protein_g: int = 0
    carbs_g: int = 0
    fat_g: int = 0


class RtRecommendationOutput(BaseModel):
    """Railtracks recommendation output schema."""
    recipe_title: str
    steps: list[str] = Field(default_factory=list)
    substitutions: list[str] = Field(default_factory=list)
    spoilage_alerts: list[str] = Field(default_factory=list)
    grocery_gap: list[RtGroceryItem] = Field(default_factory=list)
    nutrition_summary: RtNutritionSummary
    rationale: str | None = None
    confidence: float | None = None
    confidence_note: str | None = None
