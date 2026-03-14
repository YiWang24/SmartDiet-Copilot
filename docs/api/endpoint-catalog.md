# Endpoint Catalog (MVP)

Base prefix: `/api/v1`

## 1. Auth / Profile / Goals

### `GET /auth/cognito/callback`
- Purpose: map Cognito callback to app user identity bootstrap.
- Auth: public callback route with signed exchange validation.
- Response: auth/session bootstrap metadata.

### `GET /profiles/{user_id}`
- Purpose: read user onboarding profile.
- Auth: required.
- Response: profile object.

### `PUT /profiles/{user_id}`
- Purpose: create/update user profile.
- Auth: required.
- Request: profile payload.
- Response: updated profile.

### `GET /goals/{user_id}`
- Purpose: read nutrition and planning goals.
- Auth: required.
- Response: goal set.

### `PUT /goals/{user_id}`
- Purpose: create/update goals.
- Auth: required.
- Request: `ConstraintSet`.
- Response: updated goal set.

## 2. Input Ingestion

### `POST /inputs/fridge-scan`
- Purpose: submit fridge image parse task.
- Auth: required.
- Request: `FridgeScanRequest`.
- Response: `JobEnvelope` (`202 Accepted`).

### `POST /inputs/meal-scan`
- Purpose: submit meal recognition + nutrition logging task.
- Auth: required.
- Request: `MealScanRequest`.
- Response: `JobEnvelope` (`202 Accepted`).

### `POST /inputs/receipt-scan`
- Purpose: submit receipt parse task and update pantry.
- Auth: required.
- Request: `ReceiptScanRequest`.
- Response: `JobEnvelope` (`202 Accepted`).

### `POST /inputs/chat-message`
- Purpose: add conversational constraints/instructions.
- Auth: required.
- Request: `ChatMessageRequest`.
- Response: `ChatMessageResponse`.

### `GET /inputs/jobs/{job_id}`
- Purpose: retrieve ingestion job status and result payload.
- Auth: required.
- Response: `JobEnvelope`.

## 3. Planning

### `POST /planner/recommendations`
- Purpose: generate recommendation bundle.
- Auth: required.
- Request: `PlanRequest`.
- Response: recommendation metadata or async trigger.

### `POST /planner/recommendations/{recommendation_id}/replan`
- Purpose: trigger replan using latest feedback/context.
- Auth: required.
- Request: optional override constraints.
- Response: updated recommendation metadata.

### `GET /planner/recommendations/latest/{user_id}`
- Purpose: fetch latest recommendation for user.
- Auth: required.
- Response: `RecommendationBundle`.

### `GET /planner/runs/latest/{user_id}`
- Purpose: fetch latest planner run trace and execution mode (`adk` or `fallback`).
- Auth: required.
- Response: run metadata (`run_id`, `status`, `mode`, `trace_notes`, `recommendation_id`, timestamps).

## 4. Output Views

### `GET /planner/recommendations/{recommendation_id}/recipe`
- Purpose: fetch recipe detail.
- Auth: required.
- Response: includes `recipe_title`, `steps`, and `recipe_metadata` fields parsed from TheMealDB:
  - `recipe_id`, `category`, `area`, `tags`, `thumbnail_url`, `youtube_url`, `source_url`, `ingredient_details`.

### `GET /planner/recommendations/{recommendation_id}/nutrition`
- Purpose: fetch nutrition summary.
- Auth: required.

### `GET /planner/recommendations/{recommendation_id}/grocery-gap`
- Purpose: fetch minimal grocery additions.
- Auth: required.

## 5. Feedback Loop

### `PATCH /feedback/recommendations/{recommendation_id}`
- Purpose: accept/reject and refine recommendation.
- Auth: required.
- Request: `FeedbackPatch`.
- Response: `FeedbackResponse` (includes `replanned_recommendation_id` when action is `reject`).
