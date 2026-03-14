"""Authentication dependency helpers for Cognito-backed API calls."""

from __future__ import annotations

import time

import httpx
from fastapi import Depends, HTTPException, Request, status
from jose import jwt

from app.core.config import Settings, get_settings
from app.schemas.auth import AuthContext

_JWKS_CACHE: dict[str, dict] = {}
_JWKS_CACHE_TTL_SECONDS = 300


def _extract_bearer_token(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return auth_header.split(" ", 1)[1].strip()


def _dev_auth_context(request: Request) -> AuthContext:
    user_id = request.headers.get("X-Test-User-Id", "user-1")
    return AuthContext(user_id=user_id, email="dev@example.com")


def _resolve_jwks_url(settings: Settings) -> str:
    if settings.cognito_jwks_url:
        return settings.cognito_jwks_url
    if settings.cognito_issuer:
        return settings.cognito_issuer.rstrip("/") + "/.well-known/jwks.json"
    return ""


def _fetch_jwks(settings: Settings) -> dict:
    jwks_url = _resolve_jwks_url(settings)
    if not jwks_url:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Cognito JWKS URL is not configured")

    cache_key = jwks_url
    cached = _JWKS_CACHE.get(cache_key)
    now = time.time()
    if cached and now - cached["fetched_at"] < _JWKS_CACHE_TTL_SECONDS:
        return cached["jwks"]

    response = httpx.get(jwks_url, timeout=5.0)
    response.raise_for_status()
    jwks = response.json()
    _JWKS_CACHE[cache_key] = {"jwks": jwks, "fetched_at": now}
    return jwks


def _claims_auth_context(token: str, settings: Settings) -> AuthContext:
    try:
        headers = jwt.get_unverified_header(token)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token header") from exc

    kid = headers.get("kid")
    if not kid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing key id")

    try:
        jwks = _fetch_jwks(settings)
    except Exception as exc:  # pragma: no cover - network/provider failure
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unable to fetch JWKS") from exc

    key = next((item for item in jwks.get("keys", []) if item.get("kid") == kid), None)
    if not key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No matching JWKS key")

    decode_kwargs = {
        "key": key,
        "algorithms": ["RS256"],
        "issuer": settings.cognito_issuer or None,
    }
    options = {"verify_aud": bool(settings.cognito_client_id)}
    if settings.cognito_client_id:
        decode_kwargs["audience"] = settings.cognito_client_id

    try:
        claims = jwt.decode(token, options=options, **decode_kwargs)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token verification failed") from exc

    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token missing subject")

    return AuthContext(user_id=sub, email=claims.get("email"))


def get_current_user(request: Request, settings: Settings = Depends(get_settings)) -> AuthContext:
    """Resolve the authenticated user context from bearer token."""

    token = _extract_bearer_token(request)

    if settings.env != "production" and token == "fake-token":
        return _dev_auth_context(request)

    return _claims_auth_context(token, settings)
