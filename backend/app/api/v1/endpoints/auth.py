"""Authentication endpoints for Cognito integration."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user
from app.schemas.auth import AuthContext

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/cognito/callback")
async def cognito_signup_callback(
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
) -> dict:
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cognito callback error: {error}")
    if not code:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing authorization code")

    # Hackathon-safe callback: frontend can exchange code server-side in next step.
    return {
        "status": "callback_received",
        "authorization_code": code,
        "state": state,
        "next_step": "Exchange code for tokens via Cognito token endpoint",
    }


@router.get("/me")
async def me(current_user: AuthContext = Depends(get_current_user)) -> AuthContext:
    return current_user
