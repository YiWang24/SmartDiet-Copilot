# Eco-Health Agentic Dietitian

An **agentic multimodal AI dietitian assistant** that helps users eat healthier, reduce food waste, and lower grocery spending.

## Project Inspiration

Many people want to eat healthier, waste less food, and reduce their environmental footprint.  
Yet one simple question remains surprisingly difficult to answer every day: **“What should I eat today?”**

Food decisions are highly personal. The right choice depends on individual health goals, dietary restrictions, available ingredients, cooking time, and budget. However, most nutrition tools provide **generic recommendations** and mainly track what you have already eaten.

They rarely help users decide **what to cook next**, especially based on what is already in the fridge or what ingredients may expire soon.

As a result, everyday food decisions often lead to **less healthy meals, wasted ingredients, and unnecessary grocery spending.**

## Our Solution 

Build an **Agentic AI Dietitian** that understands a user's real food environment.

The system continuously reasons over:

- what users **bought** (receipt scans)
- what users **have** (fridge scans)
- what users **ate** (meal scans)
- what users **want** (goals and chat feedback)

Instead of passive tracking, the agent generates **actionable meal plans and decision guidance**.

## System Overview

This repository is a backend-first MVP using FastAPI + Railtracks architecture. The agent combines multimodal perception, user memory, constraint solving, recipe retrieval, and reflection checks to produce grounded recommendations with grocery optimization.

## User Journey Map

Sign Up and Set Goals -> Input Context -> Agent Loop -> Detailed Meal Plan Output -> User Feedback -> Agent Replans Automatically

1. **Sign Up and Set Goals**: User profile and baseline health context (age, height, weight, activity, preferences, allergies). Set personal health goals for targeted calories, macro composition. Define food restrictions, budget and time availability etc. 
2. **Provide Context**: User submits fridge image, meal image, receipt image, and optional chat instructions.
3. **Agent Loop**: System perceives, reasons over constraints, retrieves recipe knowledge, and generates strategy.
4. **Receive Output**: Recipe recommendation, instructions, nutrition breakdown, substitutions, spoilage alerts, grocery gap.
5. **Feedback Loop**: User requests changes (for example, vegetarian, lower calories, 15-minute cook time), and agent replans.

## Core Features (MVP vs Next)

> **MVP boundary for hackathon:** core planning, execution support, and memory feedback loop are in-scope.

### MVP (In Scope)

1. Receipt intelligence (extract purchased items into pantry state).
2. Fridge intelligence (detect ingredients and spoilage risk hints).
3. Meal recognition and automatic nutrition logging.
4. Agentic nutrition planner (multi-constraint meal decision).
5. Recipe retrieval via RAG-style pipeline (external recipe API in MVP).
6. Smart grocery optimization (minimal missing-ingredient list).
7. Local execution planning (calendar block + cooking DAG + proactive prep windows).
8. Long-term memory metric updates (money saved, waste reduction, sustainability impact, preference memory).

### Next (Post-MVP)

- Health and sustainability impact dashboard.
- External calendar provider integrations.
- More advanced proactive scheduling optimization policies.

## Agentic Design (Plan/Tools/Memory/Reflection/RAG Loop)

### Plan (Orchestration)

The orchestrator follows a ReAct-style loop:

1. **Perceive** multimodal user inputs.
2. **Prioritize** expiring items and hard constraints.
3. **Retrieve** profile/history and recipe candidates.
4. **Query Recipe** and formulate recommendation draft.
5. **Reflect** to validate constraints before final response.
6. **Finalize Execution Plan** (calendar + DAG + prep windows).

### Tools (Function Calling)

MVP tool contracts:

- `analyze_fridge_vision`
- `analyze_meal_vision`
- `parse_receipt_items`
- `retrieve_recipe_candidates`
- `calculate_meal_macros`
- `generate_grocery_gap`
- `decompose_cooking_workflow`
- `schedule_proactive_prep`
- `sync_to_calendar` (local persistence)

### Memory

- **Short-term state**: current session context and in-progress plan adjustments.
- **Long-term state**: persistent profile/goals/history plus favorite recipes, purchase patterns, money-saved metrics, food-waste metrics, and sustainability metrics.

### Reflection

Hard checks before final output:

- allergy and restriction compliance
- calorie/macro alignment
- spoilage-priority usage
- basic feasibility (ingredients, time)

### RAG Loop

The planner decides **what** to eat, and retrieval provides **how** to make it with grounded recipe instructions.

## Tech Stack

### Built With

- **Languages**: Python (backend), Markdown (design/docs), JavaScript/TypeScript planned for frontend
- **Backend**: FastAPI
- **Agent framework**: Railtracks orchestrator
- **Model provider**: OpenAI-compatible API
- **Auth**: AWS Cognito
- **Database**: SQLite memory-first + file snapshot storage
- **Vector Store**: Chroma memory-first + local snapshot/file modes
- **Async processing**: FastAPI `BackgroundTasks` (MVP)
- **Cache/queue (optional)**: Redis (reserved)
- **Recipe source**: External recipe API (MVP)

## Quick Start (backend run + frontend placeholder)

```bash
git clone https://github.com/YiWang24/Genai.git
cd Genai
```

Backend:

```bash
cd backend
uv sync
cp .env.example .env
uv run uvicorn app.main:app --reload --port 8000
```

Notes:
- For planner and vision parsing, set `OPENAI_API_KEY` in `backend/.env`.
- Input image URLs must be reachable by the backend service.
- Local deterministic test suite:
  `cd backend && uv run pytest -q`

Frontend:

- `frontend/` currently contains placeholder documentation only.
- Frontend implementation will consume contracts in `docs/api/openapi-contract.md`.

## Demo Flow Script (judge-friendly)

1. Create user profile and goals (or load seeded test user).
2. Submit fridge scan, receipt scan, and meal scan inputs.
3. Send a chat constraint (for example: "make it vegetarian and under 500 calories").
4. Trigger planner recommendation endpoint.
5. Show recipe output + nutrition summary + grocery gap.
6. Send feedback patch (accept/reject + message).
7. Trigger replan and show updated recommendation.

### Demo Helpers

- Seed dataset: `backend/scripts/demo_seed.json`
- One-command walkthrough (server must be running): `backend/scripts/run_demo_flow.sh`

## Video Demo Link

- Placeholder: `TBD_BEFORE_SUBMISSION`

## Future Work

- **Expand multimodal inputs:** integrate wearable health data (sleep, steps, heart rate) and lab results.
- **Refine recipe retrieval:** improve recipe diversity, filtering, and portion control.
- **Calendar integrations:** bi-directional sync for meal prep scheduling and grocery planning.
- **Shopping integration:** automatically order missing ingredients or suggest local alternatives.
- **Social features:** share meal plans and sustainability progress with friends.


