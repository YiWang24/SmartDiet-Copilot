# Eco-Health Agentic Dietitian

An agentic, multimodal dietitian assistant that helps users eat healthier, reduce food waste, and lower grocery spend.

## Project Inspiration

People want healthier eating and a lower environmental footprint, but daily food decisions are hard in practice. Most apps track past behavior but do not actively help with what to cook now, what to buy next, or what will spoil soon.

## Problem

Current nutrition workflows are fragmented:

- Users manually log meals with high friction.
- Households forget purchased ingredients and waste food.
- Nutrition goals, budget, time, and sustainability are rarely optimized together.

This creates three recurring outcomes: weaker nutrition adherence, higher food waste, and avoidable grocery costs.

## Main Idea

Build an **Agentic AI Personal Dietitian** that continuously reasons over:

- what users bought (receipt scans)
- what users have (fridge scans)
- what users ate (meal scans)
- what users want (goals, constraints, chat feedback)

The system outputs actionable meal strategy, not passive tracking.

## Solution

This repository is a backend-first MVP using FastAPI + Google ADK architecture. The agent combines multimodal perception, user memory, constraint solving, recipe retrieval, and reflection checks to produce grounded recommendations with grocery optimization.

## User Journey Map

Sign Up -> Set Goals -> Scan Fridge / Scan Meal / Scan Grocery Receipt / Send Chat Message -> Agent Loop -> Recipe + Advice + Grocery List -> User Feedback -> Agent Replans Automatically

1. **Sign Up**: User profile and baseline health context (age, height, weight, activity, preferences, allergies).
2. **Set Goals**: Targets for calories, macros, restrictions, budget, and cook time.
3. **Provide Context**: User submits fridge image, meal image, receipt image, and optional chat instructions.
4. **Agent Loop**: System perceives, reasons over constraints, retrieves recipe knowledge, and generates strategy.
5. **Receive Output**: Recipe recommendation, instructions, nutrition breakdown, substitutions, spoilage alerts, grocery gap.
6. **Feedback Loop**: User requests changes (for example, vegetarian, lower calories, 15-minute cook time), and agent replans.

## Core Features (MVP vs Next)

> **MVP boundary for hackathon:** exactly these 6 core features are in-scope. Dashboard and calendar automation are explicitly post-MVP.

### MVP (In Scope)

1. Receipt intelligence (extract purchased items into pantry state).
2. Fridge intelligence (detect ingredients and spoilage risk hints).
3. Meal recognition and automatic nutrition logging.
4. Agentic nutrition planner (multi-constraint meal decision).
5. Recipe retrieval via RAG-style pipeline (external recipe API in MVP).
6. Smart grocery optimization (minimal missing-ingredient list).

### Next (Post-MVP)

- Health and sustainability impact dashboard.
- Context-aware cooking scheduler (calendar sync).
- Deeper proactive prep DAG scheduling.

## Agentic Design (Plan/Tools/Memory/Reflection/RAG Loop)

### Plan (Orchestration)

The orchestrator follows a ReAct-style loop:

1. **Perceive** multimodal user inputs.
2. **Prioritize** expiring items and hard constraints.
3. **Retrieve** profile/history and recipe candidates.
4. **Act** by producing recommendation bundle.
5. **Reflect** to validate constraints before final response.

### Tools (Function Calling)

MVP tool contracts:

- `analyze_fridge_vision`
- `analyze_meal_vision`
- `parse_receipt_items`
- `retrieve_recipe_candidates`
- `calculate_meal_macros`
- `generate_grocery_gap`

### Memory

- **Short-term state**: current session context and in-progress plan adjustments.
- **Long-term state**: persistent profile, goals, meal history, and purchase patterns.

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
- **Agent framework**: Google ADK (planned integration contract documented)
- **Model provider**: Gemini
- **Auth**: AWS Cognito
- **Database**: PostgreSQL + pgvector
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
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

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

- Unified impact dashboard (health + climate ROI).
- Calendar-aware cooking scheduler.
- Advanced prep-task decomposition and proactive scheduling.
- Better retrieval quality with hybrid local + external recipe retrieval.
- Production-grade observability and policy controls.
