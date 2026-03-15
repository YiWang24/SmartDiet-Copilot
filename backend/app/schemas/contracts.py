"""Shared request and response contracts for MVP API endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ConstraintSet(BaseModel):
    calories_target: int | None = None
    protein_g_target: int | None = None
    carbs_g_target: int | None = None
    fat_g_target: int | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    budget_limit: float | None = None
    max_cook_time_minutes: int | None = None


class InventoryItem(BaseModel):
    ingredient: str
    quantity: str | None = None
    expires_in_days: int | None = None


class InventorySnapshot(BaseModel):
    user_id: str
    items: list[InventoryItem] = Field(default_factory=list)


class MealLog(BaseModel):
    user_id: str
    meal_name: str
    calories: int | None = None
    protein_g: int | None = None
    carbs_g: int | None = None
    fat_g: int | None = None


class PlanRequest(BaseModel):
    user_id: str
    constraints: ConstraintSet
    inventory: InventorySnapshot | None = None
    latest_meal_log: MealLog | None = None
    user_message: str | None = None
    prior_recipe_hint: dict | None = None


class ReplanRequest(BaseModel):
    constraints: ConstraintSet | None = None
    user_message: str | None = None


class NutritionSummary(BaseModel):
    calories: int
    protein_g: int
    carbs_g: int
    fat_g: int


class DailyNutritionSummary(NutritionSummary):
    meal_count: int = 0


class GroceryItem(BaseModel):
    ingredient: str
    reason: str


class RecommendationBundle(BaseModel):
    """Public planner response contract (latest, canonical V1)."""

    recommendation_id: str
    decision: "DecisionBlock"
    meal_plan: "MealPlanBlock"
    grocery_plan: "GroceryPlanBlock"
    execution_plan: "ExecutionPlanBlock"
    reflection: "ReflectionBlock"
    memory_updates: "MemoryUpdatesBlock"


class DecisionBlock(BaseModel):
    recipe_title: str
    rationale: str | None = None
    confidence: float | None = None


class MealPlanBlock(BaseModel):
    steps: list[str] = Field(default_factory=list)
    nutrition_summary: NutritionSummary
    substitutions: list[str] = Field(default_factory=list)
    spoilage_alerts: list[str] = Field(default_factory=list)


class GroceryPlanBlock(BaseModel):
    missing_ingredients: list[GroceryItem] = Field(default_factory=list)
    optimized_grocery_list: list[GroceryItem] = Field(default_factory=list)
    estimated_gap_cost: float = 0.0


class CalendarBlock(BaseModel):
    block_id: str
    title: str
    start_at: datetime
    end_at: datetime
    status: str = "scheduled"


class CookingDagTask(BaseModel):
    task_id: str
    title: str
    duration_minutes: int
    depends_on: list[str] = Field(default_factory=list)
    is_critical_path: bool = False


class ProactivePrepWindow(BaseModel):
    window_id: str
    start_at: datetime
    end_at: datetime
    assigned_task_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class ExecutionPlanBlock(BaseModel):
    calendar_blocks: list[CalendarBlock] = Field(default_factory=list)
    cooking_dag_tasks: list[CookingDagTask] = Field(default_factory=list)
    proactive_prep_windows: list[ProactivePrepWindow] = Field(default_factory=list)


class ReflectionBlock(BaseModel):
    status: str
    attempts: int
    violations: list[dict[str, Any]] = Field(default_factory=list)
    adjustments: list[str] = Field(default_factory=list)


class MemoryUpdatesBlock(BaseModel):
    short_term_updates: list[str] = Field(default_factory=list)
    long_term_metric_deltas: dict[str, Any] = Field(default_factory=dict)


class FeedbackPatch(BaseModel):
    action: Literal["accept", "reject"]
    message: str | None = None


class AgentTrace(BaseModel):
    run_id: str
    stage: Literal[
        "PERCEIVE",
        "PRIORITIZE",
        "RETRIEVE",
        "QUERY_RECIPE",
        "FORMULATE",
        "REFLECT",
        "FINALIZE",
    ]
    notes: list[str] = Field(default_factory=list)


class JobEnvelope(BaseModel):
    job_id: str
    status: JobStatus
    result: dict[str, Any] | None = None


class IngredientDetection(BaseModel):
    ingredient: str
    quantity: str | None = None
    expires_in_days: int | None = None


class FridgeScanRequest(BaseModel):
    image_url: str
    detected_items: list[IngredientDetection] = Field(default_factory=list, max_length=30)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("data:")):
            raise ValueError("image_url must be http, https, or data URL")
        return v


class MealScanRequest(BaseModel):
    image_url: str
    meal_name: str | None = None
    calories: int | None = None
    protein_g: int | None = None
    carbs_g: int | None = None
    fat_g: int | None = None

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("data:")):
            raise ValueError("image_url must be http, https, or data URL")
        return v


class ReceiptScanRequest(BaseModel):
    image_url: str
    items: list[IngredientDetection] = Field(default_factory=list, max_length=30)

    @field_validator("image_url")
    @classmethod
    def validate_image_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://") or v.startswith("data:")):
            raise ValueError("image_url must be http, https, or data URL")
        return v


class PantryItemResponse(BaseModel):
    item_id: int
    ingredient: str
    quantity: str | None = None
    expires_in_days: int | None = None
    source: str
    updated_at: datetime


class ChatMessageRequest(BaseModel):
    message: str = Field(..., max_length=2000)


class ChatMessageResponse(BaseModel):
    event_id: int
    user_id: str
    message: str
    assistant_message: str | None = None
    recommendation: RecommendationBundle | None = None


class ChatMessageEvent(BaseModel):
    event_id: int
    user_id: str
    role: Literal["user", "assistant"] = "user"
    source: Literal["turn", "legacy"] = "legacy"
    message: str
    created_at: datetime
    recommendation_id: str | None = None


class FeedbackResponse(BaseModel):
    event_id: int
    recommendation_id: str
    action: Literal["accept", "reject"]
    message: str | None = None
    replanned_recommendation_id: str | None = None
