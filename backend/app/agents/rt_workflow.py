"""Railtracks agentic workflow orchestrator for meal planning."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

import railtracks as rt

from app.agents.io_contracts import AgentPlanInputV1, AgentPlanOutputV1
from app.agents.reflection import apply_reflection
from app.agents.rt_config import get_llm, get_vector_store
from app.agents.schemas import AgentDraftBundle, RtRecommendationOutput
from app.agents.tools import (
    calculate_meal_macros,
    decompose_cooking_workflow,
    generate_grocery_gap_tool,
    retrieve_recipe_candidates,
    schedule_proactive_prep,
)
from app.core.config import Settings, get_settings
from app.schemas.contracts import (
    DecisionBlock,
    ExecutionPlanBlock,
    GroceryItem,
    GroceryPlanBlock,
    MealPlanBlock,
    MemoryUpdatesBlock,
    PlanRequest,
    ReflectionBlock,
)
from app.services.execution_planning import build_cooking_dag_tasks, build_proactive_prep_windows
from app.services.planner import retrieve_recipe_candidates as retrieve_recipe_candidates_service
from app.agents.rag_pipeline import get_rag_pipeline


class RailtracksAgenticWorkflow:
    """Stage-based Railtracks workflow following the agentic design loop."""

    def __init__(self, settings: Settings):
        self.settings = settings
        resolved_api_key = (settings.gemini_api_key or "").strip()
        self._enabled = bool(
            settings.railtracks_enabled
            and resolved_api_key
            and (settings.gemini_model or settings.railtracks_model)
        )
        self._llm = None
        self._vector_store = None
        self._agent = None
        self._rag = get_rag_pipeline()

        if not self._enabled:
            return

        try:
            self._llm = get_llm()
            self._vector_store = get_vector_store()
            self._agent = self._build_agent()
        except Exception:  # pragma: no cover - environment dependent
            self._enabled = False

    def _build_agent(self):
        instruction = (
            "You are SmartDiet Copilot, an expert AI dietitian meal planner. "
            "Your core priorities, in strict order:\n"
            "1. HONOR the user's explicit request (user_message) — this is the primary intent.\n"
            "2. USE expiring ingredients first — any item with expires_in_days <= 3 MUST appear in the recipe.\n"
            "3. MINIMIZE grocery gap — prefer recipes that use what is already in inventory.\n"
            "4. ENFORCE constraints — allergies and dietary_restrictions are hard rules; never violate them.\n"
            "5. PROVIDE accurate nutrition — estimate calories, protein, carbs, fat realistically for the recipe.\n\n"
            "Output ONLY valid JSON with these exact fields:\n"
            "{\n"
            '  "recipe_title": "string — specific dish name",\n'
            '  "steps": ["step 1", "step 2", ...],\n'
            '  "substitutions": ["ingredient swap suggestion if needed"],\n'
            '  "spoilage_alerts": ["Use <ingredient> within X days"],\n'
            '  "grocery_gap": [{"ingredient": "name", "reason": "why needed"}],\n'
            '  "nutrition_summary": {"calories": int, "protein_g": int, "carbs_g": int, "fat_g": int},\n'
            '  "rationale": "1-2 sentences explaining why this recipe fits the request and inventory",\n'
            '  "confidence": 0.0-1.0\n'
            "}\n"
            "Set confidence >= 0.8 only when the recipe directly uses expiring ingredients AND satisfies user_message. "
            "If no good match exists, pick the closest recipe and explain the gap in rationale."
        )
        tools = [
            retrieve_recipe_candidates,
            calculate_meal_macros,
            generate_grocery_gap_tool,
            decompose_cooking_workflow,
            schedule_proactive_prep,
        ]
        if hasattr(rt, "Agent"):
            if self._vector_store:
                return rt.Agent(
                    name="eco_health_agentic_planner",
                    llm=self._llm,
                    instruction=instruction,
                    tools=tools,
                    vector_store=self._vector_store,
                    output_schema=RtRecommendationOutput,
                )
            return rt.Agent(
                name="eco_health_agentic_planner",
                llm=self._llm,
                instruction=instruction,
                tools=tools,
                output_schema=RtRecommendationOutput,
            )

        rag_config = rt.RagConfig(vector_store=self._vector_store, top_k=3) if self._vector_store else None
        return rt.agent_node(
            name="eco_health_agentic_planner",
            llm=self._llm,
            system_message=instruction,
            tool_nodes=tools,
            rag=rag_config,
            output_schema=RtRecommendationOutput,
        )

    async def recommend_async(self, agent_input: AgentPlanInputV1) -> AgentPlanOutputV1:
        if not self._enabled or not self._agent:
            raise RuntimeError("Railtracks workflow is disabled or unavailable")

        trace_notes: list[str] = ["workflow:railtracks-agentic"]

        request = self.perceive(agent_input)
        trace_notes.append("stage:PERCEIVE")

        priority_signals = self.prioritize(request)
        trace_notes.append("stage:PRIORITIZE")

        retrieved_context = self.retrieve_context(request, priority_signals)
        trace_notes.append("stage:RETRIEVE")

        candidates = self.query_recipe(request, priority_signals, retrieved_context)
        trace_notes.append(f"stage:QUERY_RECIPE:candidates={len(candidates)}")

        output = await self.reflect_and_retry(
            request=request,
            candidates=candidates,
            priority_signals=priority_signals,
            retrieved_context=retrieved_context,
            trace_notes=trace_notes,
        )
        trace_notes.append("stage:REFLECT")

        final_execution = self.finalize_execution(output.meal_plan.steps)
        output.execution_plan = final_execution
        output.trace_notes = trace_notes
        trace_notes.append("stage:FINALIZE")
        return output

    @staticmethod
    def perceive(agent_input: AgentPlanInputV1) -> PlanRequest:
        """Perceive stage: normalize incoming runtime context."""

        return agent_input.to_plan_request()

    @staticmethod
    def prioritize(request: PlanRequest) -> dict[str, Any]:
        """Prioritize stage: identify spoilage and hard constraints."""

        expiring_critical: list[str] = []
        expiring_soon: list[str] = []
        if request.inventory and request.inventory.items:
            for item in request.inventory.items:
                if item.expires_in_days is None or not item.ingredient:
                    continue
                if item.expires_in_days <= 1:
                    expiring_critical.append(item.ingredient)
                elif item.expires_in_days <= 3:
                    expiring_soon.append(item.ingredient)
            expiring_critical = sorted(expiring_critical)
            expiring_soon = sorted(expiring_soon)

        return {
            "expiring_critical": expiring_critical[:5],   # must use today
            "expiring_soon": expiring_soon[:8],            # should use this week
            "expiring_ingredients": expiring_critical[:5] + expiring_soon[:5],
            "allergies": request.constraints.allergies,
            "dietary_restrictions": request.constraints.dietary_restrictions,
            "max_cook_time_minutes": request.constraints.max_cook_time_minutes,
            "calories_target": request.constraints.calories_target,
            "user_message": request.user_message,
        }

    def retrieve_context(self, request: PlanRequest, priority_signals: dict[str, Any]) -> list[dict[str, Any]]:
        """Retrieve stage: gather vector/keyword recipe context."""

        _ = priority_signals
        try:
            return self._rag.retrieve_context(request.inventory, request.constraints, limit=5)
        except Exception:
            return []

    @staticmethod
    def query_recipe(
        request: PlanRequest,
        priority_signals: dict[str, Any],
        retrieved_context: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Query recipe stage: produce candidate recipe set."""

        _ = priority_signals
        candidates = retrieve_recipe_candidates_service(
            request.inventory,
            constraints=request.constraints,
            limit=5,
        )
        if candidates:
            return candidates

        rag_backfill = [item.get("full_recipe") for item in retrieved_context if isinstance(item.get("full_recipe"), dict)]
        return [item for item in rag_backfill if item]

    async def formulate_plan(
        self,
        *,
        request: PlanRequest,
        candidate_recipe: dict[str, Any] | None,
        priority_signals: dict[str, Any],
        retrieved_context: list[dict[str, Any]],
        attempt: int,
    ) -> tuple[AgentDraftBundle, dict[str, Any]]:
        """Formulate stage: use Railtracks to draft recommendation payload."""

        prompt = self._build_prompt(
            request=request,
            candidate_recipe=candidate_recipe,
            priority_signals=priority_signals,
            retrieved_context=retrieved_context,
            attempt=attempt,
        )
        if hasattr(self._agent, "run_async"):
            result = await self._agent.run_async(prompt)
        else:
            result = await rt.call(self._agent, prompt)

        content = getattr(result, "content", result)
        if not content:
            raise ValueError("No Railtracks response content produced")

        parsed = self._parse_railtracks_output(content)
        from app.schemas.contracts import NutritionSummary
        bundle = AgentDraftBundle(
            recipe_title=parsed.recipe_title,
            steps=parsed.steps,
            substitutions=parsed.substitutions,
            spoilage_alerts=parsed.spoilage_alerts,
            grocery_gap=[GroceryItem.model_validate(item.model_dump()) for item in parsed.grocery_gap],
            nutrition_summary=NutritionSummary.model_validate(parsed.nutrition_summary.model_dump()),
        )
        decision = {
            "rationale": parsed.rationale or parsed.confidence_note,
            "confidence": parsed.confidence,
        }
        return bundle, decision

    async def reflect_and_retry(
        self,
        *,
        request: PlanRequest,
        candidates: list[dict[str, Any]],
        priority_signals: dict[str, Any],
        retrieved_context: list[dict[str, Any]],
        trace_notes: list[str],
    ) -> AgentPlanOutputV1:
        """Reflect stage with bounded retries."""

        max_attempts = 3
        adjustments: list[str] = []
        final_bundle: AgentDraftBundle | None = None
        final_violations: list[dict[str, Any]] = []
        final_decision_meta: dict[str, Any] = {}
        status = "ok"
        attempts_used = 0

        for attempt in range(1, max_attempts + 1):
            attempts_used = attempt
            candidate_recipe = candidates[(attempt - 1) % len(candidates)] if candidates else None
            bundle, decision_meta = await self.formulate_plan(
                request=request,
                candidate_recipe=candidate_recipe,
                priority_signals=priority_signals,
                retrieved_context=retrieved_context,
                attempt=attempt,
            )

            reflected_bundle, notes, violations = apply_reflection(bundle, request)
            trace_notes.append(f"attempt:{attempt}")
            trace_notes.extend([f"reflection:{note}" for note in notes])
            trace_notes.extend([f"violation:{item.get('type', 'unknown')}" for item in violations])

            adjustments.extend(notes)
            final_bundle = reflected_bundle
            final_violations = violations
            final_decision_meta = decision_meta

            confidence = decision_meta.get("confidence") or 0.0
            if not violations and confidence >= 0.5:
                status = "ok"
                break
            if violations:
                status = "adjusted_with_violations"
            else:
                status = "low_confidence_retry"
                trace_notes.append(f"low_confidence:{confidence:.2f}")

        if final_bundle is None:
            raise RuntimeError("Unable to formulate recommendation after retries")

        return AgentPlanOutputV1(
            decision=DecisionBlock(
                recipe_title=final_bundle.recipe_title,
                rationale=final_decision_meta.get("rationale"),
                confidence=final_decision_meta.get("confidence"),
            ),
            meal_plan=MealPlanBlock(
                steps=final_bundle.steps,
                nutrition_summary=final_bundle.nutrition_summary,
                substitutions=final_bundle.substitutions,
                spoilage_alerts=final_bundle.spoilage_alerts,
            ),
            grocery_plan=GroceryPlanBlock(
                missing_ingredients=final_bundle.grocery_gap,
                optimized_grocery_list=final_bundle.grocery_gap,
                estimated_gap_cost=float(len(final_bundle.grocery_gap) * 2.0),
            ),
            execution_plan=ExecutionPlanBlock(),
            reflection=ReflectionBlock(
                status=status,
                attempts=attempts_used,
                violations=final_violations,
                adjustments=adjustments,
            ),
            memory_updates=MemoryUpdatesBlock(
                short_term_updates=["inventory_used", "constraints_applied", "chat_context_applied"],
                long_term_metric_deltas={},
            ),
            trace_notes=trace_notes,
            mode="railtracks-agentic",
        )

    @staticmethod
    def finalize_execution(steps: list[str]) -> ExecutionPlanBlock:
        """Finalize stage: build non-persisted execution plan preview."""

        tasks = build_cooking_dag_tasks(steps)
        windows = build_proactive_prep_windows(tasks)
        return ExecutionPlanBlock(
            calendar_blocks=[],
            cooking_dag_tasks=tasks,
            proactive_prep_windows=windows,
        )

    @staticmethod
    def _parse_railtracks_output(content: Any) -> RtRecommendationOutput:
        if isinstance(content, RtRecommendationOutput):
            return content

        if isinstance(content, dict):
            return RtRecommendationOutput.model_validate(content)

        if hasattr(content, "model_dump"):
            return RtRecommendationOutput.model_validate(content.model_dump())

        content = str(content).strip()
        try:
            return RtRecommendationOutput.model_validate_json(content)
        except Exception:
            pass

        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("Unable to parse Railtracks JSON output")
        payload = json.loads(match.group(0))
        return RtRecommendationOutput.model_validate(payload)

    @staticmethod
    def _build_prompt(
        *,
        request: PlanRequest,
        candidate_recipe: dict[str, Any] | None,
        priority_signals: dict[str, Any],
        retrieved_context: list[dict[str, Any]],
        attempt: int,
    ) -> str:
        lines: list[str] = []

        # ── USER REQUEST (top priority) ──────────────────────────────────────
        user_msg = request.user_message or priority_signals.get("user_message") or ""
        if user_msg:
            lines.append(f"## USER REQUEST\n{user_msg}")

        # ── EXPIRING INGREDIENTS (must use) ──────────────────────────────────
        critical = priority_signals.get("expiring_critical", [])
        soon = priority_signals.get("expiring_soon", [])
        if critical:
            lines.append(f"## CRITICAL — USE TODAY (expires ≤1 day)\n{', '.join(critical)}")
        if soon:
            lines.append(f"## USE SOON (expires ≤3 days)\n{', '.join(soon)}")

        # ── FULL INVENTORY ───────────────────────────────────────────────────
        if request.inventory and request.inventory.items:
            inv_lines = []
            for item in request.inventory.items[:20]:
                exp = f" (expires in {item.expires_in_days}d)" if item.expires_in_days is not None else ""
                qty = f" — {item.quantity}" if item.quantity else ""
                inv_lines.append(f"  • {item.ingredient}{qty}{exp}")
            lines.append("## AVAILABLE INVENTORY\n" + "\n".join(inv_lines))

        # ── CONSTRAINTS ──────────────────────────────────────────────────────
        constraints_parts: list[str] = []
        if priority_signals.get("allergies"):
            constraints_parts.append(f"Allergies (NEVER include): {', '.join(priority_signals['allergies'])}")
        if priority_signals.get("dietary_restrictions"):
            constraints_parts.append(f"Dietary restrictions: {', '.join(priority_signals['dietary_restrictions'])}")
        if priority_signals.get("max_cook_time_minutes"):
            constraints_parts.append(f"Max cook time: {priority_signals['max_cook_time_minutes']} minutes")
        if priority_signals.get("calories_target"):
            constraints_parts.append(f"Calorie target: {priority_signals['calories_target']} kcal")
        if constraints_parts:
            lines.append("## CONSTRAINTS\n" + "\n".join(constraints_parts))

        # ── CANDIDATE RECIPE ─────────────────────────────────────────────────
        if candidate_recipe:
            recipe_summary = {
                "title": candidate_recipe.get("recipe_title"),
                "ingredients": candidate_recipe.get("ingredients", [])[:15],
                "steps_preview": (candidate_recipe.get("steps") or candidate_recipe.get("instructions", ""))[:300],
                "category": candidate_recipe.get("category"),
            }
            lines.append(f"## CANDIDATE RECIPE (adapt or replace if poor fit)\n{json.dumps(recipe_summary, ensure_ascii=True)}")

        # ── RAG CONTEXT ──────────────────────────────────────────────────────
        relevant = [
            ctx.get("recipe_title") or ctx.get("full_recipe", {}).get("recipe_title")
            for ctx in retrieved_context[:3]
            if ctx.get("recipe_title") or (ctx.get("full_recipe") or {}).get("recipe_title")
        ]
        if relevant:
            lines.append(f"## OTHER RELEVANT RECIPES (use for inspiration if candidate is poor fit)\n{', '.join(filter(None, relevant))}")

        # ── ATTEMPT NOTE ─────────────────────────────────────────────────────
        if attempt > 1:
            lines.append(
                f"## RETRY ATTEMPT {attempt}\n"
                "Previous attempt had low confidence. Choose a DIFFERENT recipe that better uses "
                "the expiring ingredients and directly answers the user request."
            )

        # ── FINAL INSTRUCTION ────────────────────────────────────────────────
        lines.append(
            "## TASK\n"
            "Choose the BEST recipe given the above context. If the candidate recipe fits well, adapt it. "
            "If it conflicts with constraints or ignores expiring ingredients, REPLACE it with a better option.\n"
            "Return ONLY the JSON object — no markdown, no explanation outside the JSON."
        )

        return "\n\n".join(lines)

@lru_cache(maxsize=1)
def get_railtracks_workflow() -> RailtracksAgenticWorkflow:
    """Return cached Railtracks workflow instance."""
    return RailtracksAgenticWorkflow(get_settings())
