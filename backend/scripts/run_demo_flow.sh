#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TOKEN="${TOKEN:-fake-token}"
USER_ID="${USER_ID:-demo-user-001}"
SEED_FILE="${SEED_FILE:-$(dirname "$0")/demo_seed.json}"

if [[ ! -f "$SEED_FILE" ]]; then
  echo "Seed file not found: $SEED_FILE" >&2
  exit 1
fi

export BASE_URL TOKEN USER_ID SEED_FILE

json_get() {
  python3 - "$1" <<'PY'
import json
import os
import sys

expr = sys.argv[1]
with open(os.environ["SEED_FILE"], "r", encoding="utf-8") as f:
    data = json.load(f)

value = data
for token in expr.split('.'):
    if token.endswith(']'):
        key, idx = token[:-1].split('[')
        value = value[key][int(idx)]
    else:
        value = value[token]
print(json.dumps(value))
PY
}

api() {
  local method="$1"
  local path="$2"
  local body="${3:-}"

  if [[ -n "$body" ]]; then
    curl -sS -X "$method" "$BASE_URL$path" \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Test-User-Id: $USER_ID" \
      -H "Content-Type: application/json" \
      -d "$body"
  else
    curl -sS -X "$method" "$BASE_URL$path" \
      -H "Authorization: Bearer $TOKEN" \
      -H "X-Test-User-Id: $USER_ID"
  fi
}

echo "==> Upsert profile"
PROFILE_PAYLOAD="$(json_get profile)"
api PUT "/api/v1/profiles/$USER_ID" "$PROFILE_PAYLOAD" | python3 -m json.tool

echo "==> Upsert goals"
GOALS_PAYLOAD="$(json_get goals)"
api PUT "/api/v1/goals/$USER_ID" "$GOALS_PAYLOAD" | python3 -m json.tool

echo "==> Submit fridge scan"
FRIDGE_PAYLOAD="$(json_get fridge_scan)"
api POST "/api/v1/inputs/fridge-scan" "$FRIDGE_PAYLOAD" | python3 -m json.tool

echo "==> Submit meal scan"
MEAL_PAYLOAD="$(json_get meal_scan)"
api POST "/api/v1/inputs/meal-scan" "$MEAL_PAYLOAD" | python3 -m json.tool

echo "==> Submit receipt scan"
RECEIPT_PAYLOAD="$(json_get receipt_scan)"
api POST "/api/v1/inputs/receipt-scan" "$RECEIPT_PAYLOAD" | python3 -m json.tool

echo "==> Send chat message"
CHAT_PAYLOAD="$(json_get chat_message)"
api POST "/api/v1/inputs/chat-message" "$CHAT_PAYLOAD" | python3 -m json.tool

echo "==> Create recommendation"
PLAN_REQUEST="$(python3 - <<'PY'
import json
import os

with open(os.environ["SEED_FILE"], "r", encoding="utf-8") as f:
    data = json.load(f)

plan = data["plan_request"]
plan["user_id"] = os.environ["USER_ID"]
plan["inventory"]["user_id"] = os.environ["USER_ID"]
print(json.dumps(plan))
PY
)"
REC_RESPONSE="$(api POST "/api/v1/planner/recommendations" "$PLAN_REQUEST")"
echo "$REC_RESPONSE" | python3 -m json.tool

REC_ID="$(echo "$REC_RESPONSE" | python3 - <<'PY'
import json
import sys

print(json.load(sys.stdin)["recommendation_id"])
PY
)"

echo "==> Submit feedback (reject triggers replan)"
FEEDBACK_PAYLOAD="$(json_get feedback)"
FEEDBACK_RESPONSE="$(api PATCH "/api/v1/feedback/recommendations/$REC_ID" "$FEEDBACK_PAYLOAD")"
echo "$FEEDBACK_RESPONSE" | python3 -m json.tool

echo "==> Latest recommendation"
api GET "/api/v1/planner/recommendations/latest/$USER_ID" | python3 -m json.tool

echo "Demo flow completed."
