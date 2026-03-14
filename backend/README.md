# Backend (FastAPI + Google ADK)

This backend hosts the MVP APIs for **Eco-Health Agentic Dietitian**.

## Current Status

- Backend MVP flows are implemented end-to-end for hackathon demo.
- Agent workflow supports ADK execution with safe fallback mode.
- Core docs in `/docs` are aligned with implemented contracts.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Environment

Copy and edit:

```bash
cp .env.example .env
```

Required contract (MVP):

- `GEMINI_API_KEY`
- `ADK_ENABLED`
- `ADK_MODEL`
- `COGNITO_REGION`
- `COGNITO_USER_POOL_ID`
- `COGNITO_CLIENT_ID`
- `COGNITO_ISSUER`
- `RECIPE_API_BASE_URL`
- `RECIPE_API_KEY`
- `DATABASE_URL`
- `REDIS_URL` (optional for this phase)

## ADK Workflow Mode

- If `ADK_ENABLED=true` and `GEMINI_API_KEY` is set, planner routes use Google ADK orchestrator.
- If ADK is disabled/unavailable, planner automatically falls back to deterministic local workflow.

## Recipe API Integration

TheMealDB integration uses free endpoints in this order:

1. `filter.php?i=<ingredient>` for candidate IDs (single-ingredient free tier)
2. `lookup.php?i=<idMeal>` for full meal details
3. `search.php?s=<query>` and `random.php` as fallback

Parsed fields include recipe id, category, area, thumbnail, source links, and ingredient-measure pairs.
