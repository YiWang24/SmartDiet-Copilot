"""Gemini Vision integration utilities for fridge/meal/receipt parsing."""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
_DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _guess_mime_type(image_ref: str, default_mime: str = "image/jpeg") -> str:
    lower = image_ref.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".gif"):
        return "image/gif"
    return default_mime


def _load_image_bytes(image_ref: str) -> tuple[bytes, str] | None:
    """Load image from various sources and return (bytes, mime_type)."""

    image_ref = image_ref.strip()
    data_url_match = _DATA_URL_RE.match(image_ref)
    if data_url_match:
        mime = data_url_match.group("mime")
        decoded = base64.b64decode(data_url_match.group("data"))
        return decoded, mime

    if image_ref.startswith("http://") or image_ref.startswith("https://"):
        try:
            response = httpx.get(image_ref, timeout=12.0)
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            mime_type = content_type.split(";", 1)[0].strip() or _guess_mime_type(image_ref)
            if not mime_type.startswith("image/"):
                mime_type = _guess_mime_type(image_ref)
            return response.content, mime_type
        except Exception:
            return None

    local = Path(image_ref).expanduser()
    if local.exists() and local.is_file():
        mime_type = _guess_mime_type(local.name)
        return local.read_bytes(), mime_type

    return None


def _normalize_model_resource(model_name: str) -> str:
    model = (model_name or "").strip()
    if model.startswith("models/"):
        return model
    if model.startswith("gemini/"):
        model = model.split("/", 1)[1]
    if not model:
        model = "gemini-2.5-pro"
    return f"models/{model}"


def _extract_text_from_gemini_response(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            text = part.get("text")
            if text:
                return str(text)
    return ""


def _generate_structured_json(image_ref: str, prompt: str) -> dict[str, Any] | None:
    settings = get_settings()
    api_key = (settings.gemini_api_key or "").strip()
    if not api_key:
        return None

    image_result = _load_image_bytes(image_ref)
    if not image_result:
        return None

    image_bytes, mime_type = image_result
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    model = _normalize_model_resource(settings.gemini_vision_model or settings.gemini_model)
    url = f"{_GEMINI_API_BASE}/{model}:generateContent"
    base_payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_b64}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json",
        },
    }

    try:
        response = httpx.post(
            url,
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=base_payload,
            timeout=30.0,
        )
        response.raise_for_status()
        text = _extract_text_from_gemini_response(response.json())
        return _extract_json_object(text)
    except Exception:
        # Compatibility fallback for models/endpoints that ignore responseMimeType.
        fallback_payload = {
            "contents": base_payload["contents"],
            "generationConfig": {"temperature": 0.1},
        }
        try:
            response = httpx.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=fallback_payload,
                timeout=30.0,
            )
            response.raise_for_status()
            text = _extract_text_from_gemini_response(response.json())
            return _extract_json_object(text)
        except Exception:
            return None


def _normalize_ingredient_rows(
    rows: list[dict[str, Any]] | None,
    *,
    default_expires: int,
    limit: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in rows or []:
        ingredient = str(item.get("ingredient") or "").strip().lower()
        if not ingredient:
            continue
        quantity = item.get("quantity")
        expires = item.get("expires_in_days")
        try:
            expires_int = int(expires) if expires is not None else default_expires
        except Exception:
            expires_int = default_expires
        expires_int = max(0, min(expires_int, 30))

        normalized.append(
            {
                "ingredient": ingredient,
                "quantity": str(quantity).strip() if quantity else None,
                "expires_in_days": expires_int,
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def parse_fridge_ingredients_with_gemini(image_ref: str) -> list[dict[str, Any]]:
    """Parse fridge image into normalized ingredient items using Gemini Vision."""

    prompt = (
        "You are extracting ingredients from a fridge image. "
        "Return strict JSON object with key 'ingredients' only. "
        "Each ingredient item must contain: ingredient (lowercase English), quantity, expires_in_days (integer 0-30). "
        "Do not include markdown."
    )
    payload = _generate_structured_json(image_ref, prompt)
    if not payload:
        return []
    return _normalize_ingredient_rows(payload.get("ingredients"), default_expires=3, limit=16)


def parse_meal_with_gemini(image_ref: str) -> dict[str, Any] | None:
    """Parse meal image, estimate nutrition, and produce dietary analysis using Gemini Vision."""

    prompt = (
        "You are a registered dietitian analyzing a meal photo. "
        "Identify the dish and estimate its nutritional content. "
        "Return a strict JSON object with EXACTLY these keys:\n"
        '  "meal_name": string — specific dish name\n'
        '  "calories": integer — total estimated kcal\n'
        '  "protein_g": integer — grams of protein\n'
        '  "carbs_g": integer — grams of carbohydrates\n'
        '  "fat_g": integer — grams of fat\n'
        '  "highlights": array of 2-3 short strings — genuine nutritional strengths '
        "(e.g. 'Rich in lean protein', 'Good source of fiber', 'Low saturated fat')\n"
        '  "suggestions": array of 2-3 short strings — actionable improvements '
        "(e.g. 'Add leafy greens for micronutrients', 'Swap white rice for brown rice', "
        "'Reduce portion size to lower calories')\n"
        "All macro values must be positive integers. highlights and suggestions must each have 2-3 items."
    )
    payload = _generate_structured_json(image_ref, prompt)
    if not payload:
        return None

    meal_name = str(payload.get("meal_name") or "").strip()

    def _safe_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
            return max(0, parsed)
        except Exception:
            return default

    def _safe_str_list(value: Any, default: list[str]) -> list[str]:
        if not isinstance(value, list):
            return default
        return [str(item).strip() for item in value if str(item).strip()][:3] or default

    return {
        "meal_name": meal_name or "recognized meal",
        "calories": _safe_int(payload.get("calories"), 520),
        "protein_g": _safe_int(payload.get("protein_g"), 28),
        "carbs_g": _safe_int(payload.get("carbs_g"), 46),
        "fat_g": _safe_int(payload.get("fat_g"), 20),
        "highlights": _safe_str_list(
            payload.get("highlights"),
            ["Provides essential macronutrients", "Balanced meal composition"],
        ),
        "suggestions": _safe_str_list(
            payload.get("suggestions"),
            ["Add more vegetables for fiber and vitamins", "Consider portion size for calorie goals"],
        ),
    }


def parse_receipt_with_gemini(image_ref: str) -> list[dict[str, Any]]:
    """Parse receipt image into normalized purchased items using Gemini Vision."""

    prompt = (
        "Extract grocery items from this shopping receipt image. "
        "Return strict JSON object with key 'items' only. "
        "Each item must contain: ingredient (lowercase English), quantity, expires_in_days (integer 0-30 estimated shelf life). "
        "Do not include non-food products."
    )
    payload = _generate_structured_json(image_ref, prompt)
    if not payload:
        return []
    return _normalize_ingredient_rows(payload.get("items"), default_expires=5, limit=20)
