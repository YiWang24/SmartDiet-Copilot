# Backend System Design

## 1. Architecture Style

This MVP uses a **modular monolith** backend:

- **Framework**: FastAPI
- **Agent orchestration**: Google ADK (orchestrator + tool adapters)
- **Data**: PostgreSQL + pgvector
- **Authentication**: AWS Cognito
- **Recipe knowledge source**: external recipe API
- **Async execution model**: synchronous API with `BackgroundTasks` for vision parsing and replanning

Why this shape for hackathon:

- Faster delivery than microservices.
- Clear module boundaries for future extraction.
- Enough structure for reliable demo and extension.

## 2. Runtime Flow

### 2.1 Request Handling

1. Client calls FastAPI endpoint with Cognito bearer token.
2. API validates token, normalizes payload, persists event.
3. For heavy operations (image analysis, replan), API schedules `BackgroundTasks` and returns `JobEnvelope`.
4. Background task executes tool calls and writes results.
5. Client polls job/recommendation endpoints for final output.

### 2.2 Sync + Async Split

- **Sync**: profile/goals CRUD, plan trigger, recommendation read paths.
- **Async**: fridge scan parse, meal scan parse, receipt parse, complex replan chain.

## 3. Domain Modules

- `auth`: Cognito token verification and identity mapping.
- `profiles`: onboarding profile and user preferences.
- `goals`: nutrition targets, dietary restrictions, budget/time constraints.
- `inventory`: pantry state and receipt/fridge updates.
- `intake`: meal logs and macro progress state.
- `planner`: plan request, recommendation generation, replan triggers.
- `recipes`: retrieval adapter and recipe normalization.
- `feedback`: accept/reject signals and iterative adjustment history.

## 4. Data Model Definitions

## 4.1 Core Entities

| Entity | Purpose | Key Fields |
|---|---|---|
| `users` | app-level user identity mapped from Cognito | `id`, `cognito_sub`, `email`, `created_at` |
| `goals` | nutrition and lifestyle constraints | `user_id`, `calories_target`, `protein_target`, `dietary_restrictions`, `budget_limit`, `max_cook_time` |
| `pantry_items` | current inventory and expiry context | `user_id`, `ingredient`, `quantity`, `source`, `expires_at`, `updated_at` |
| `receipt_events` | raw + parsed receipt ingestion record | `user_id`, `image_uri`, `parsed_items`, `created_at` |
| `meal_logs` | recognized meals and macros | `user_id`, `meal_name`, `calories`, `protein_g`, `carbs_g`, `fat_g`, `eaten_at` |
| `plan_runs` | agent run metadata and lifecycle | `id`, `user_id`, `status`, `request_payload`, `trace`, `created_at` |
| `recommendations` | actionable meal plan output | `id`, `plan_run_id`, `recipe_title`, `steps`, `nutrition_summary`, `grocery_gap`, `created_at` |
| `feedback_events` | user accept/reject and instruction deltas | `user_id`, `recommendation_id`, `action`, `message`, `created_at` |

## 4.2 Vector/Similarity Support

- `recipe_embeddings` table (or materialized view) in PostgreSQL with pgvector for retrieval hints.
- During MVP, external recipe API remains source-of-truth; pgvector is reserved for hybrid retrieval next step.

## 5. Agent Loop and Failure Fallback

## 5.1 Sequence

1. **Perceive**: parse input modalities and normalize signals.
2. **Reason**: combine goals, current intake, inventory freshness, budget/time.
3. **Retrieve**: fetch recipe candidates using structured constraints.
4. **Act**: produce recommendation bundle + grocery gap.
5. **Reflect**: validate hard constraints before response finalization.

## 5.2 Failure Fallback Strategy

- Vision parse failure: keep prior state and request manual confirmation.
- Recipe API timeout: use cached candidate or return constrained fallback meal template.
- Constraint violation after reflect: auto-retry with stricter filters once, then return safe minimal option.
- Async task crash: mark job `FAILED`, include `trace_id`, and expose retryable reason.

## 6. Non-Functional Requirements (Hackathon)

## 6.1 Latency Targets

- Sync CRUD endpoints: p95 < 300 ms
- Plan trigger endpoint: p95 < 600 ms (queueing accepted)
- Async completion for scans/replan: typically < 20 s in demo environment

## 6.2 Graceful Degradation

- If vision provider unavailable, permit manual ingredient input route (next implementation task).
- If recipe provider unavailable, return constrained baseline recipe pattern and missing data warning.

## 6.3 Observability Basics

- Structured JSON logs with `trace_id`, `user_id`, `plan_run_id`.
- Basic metrics: request count, error count, async job state distribution.
- Health endpoint for uptime checks.

## 7. Security and Compliance Baseline

- Cognito JWT verification at API boundary (JWKS signature validation).
- No secrets in repository; use environment contract.
- PII minimization in logs (mask email/image URLs where needed).
- Basic rate limiting and payload size guards for image endpoints (implementation phase).

## 8. Deployment Notes (MVP)

- Single FastAPI service container.
- Managed PostgreSQL instance with pgvector extension enabled.
- Optional Redis reserved but not required in current `BackgroundTasks` mode.
- Environment-specific config via `.env` in dev and secret manager in hosted deployment.
