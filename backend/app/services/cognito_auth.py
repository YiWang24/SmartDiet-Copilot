"""AWS Cognito auth helpers for sign-up, confirmation and login flows."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import string

import httpx
from fastapi import HTTPException, status

from app.core.config import Settings


def _require_cognito_client(settings: Settings) -> None:
    if not settings.cognito_region or not settings.cognito_client_id:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Cognito client is not configured on the backend",
        )


def _secret_hash(username: str, settings: Settings) -> str | None:
    if not settings.cognito_client_secret:
        return None

    digest = hmac.new(
        settings.cognito_client_secret.encode("utf-8"),
        (username + settings.cognito_client_id).encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return base64.b64encode(digest).decode("utf-8")


def _cognito_endpoint(settings: Settings) -> str:
    return f"https://cognito-idp.{settings.cognito_region}.amazonaws.com/"


def _extract_cognito_error(payload: dict) -> tuple[str, str]:
    raw_type = str(payload.get("__type") or "CognitoException")
    error_name = raw_type.split("#")[-1]
    message = str(payload.get("message") or "Cognito request failed")
    return error_name, message


def _map_cognito_http_status(error_name: str) -> int:
    if error_name in {"UsernameExistsException", "CodeMismatchException", "InvalidPasswordException"}:
        return status.HTTP_400_BAD_REQUEST
    if error_name in {"UserNotFoundException", "NotAuthorizedException"}:
        return status.HTTP_401_UNAUTHORIZED
    if error_name in {"UserNotConfirmedException", "ExpiredCodeException"}:
        return status.HTTP_403_FORBIDDEN
    if error_name in {"TooManyRequestsException", "LimitExceededException"}:
        return status.HTTP_429_TOO_MANY_REQUESTS
    return status.HTTP_502_BAD_GATEWAY


def _call_cognito(target: str, payload: dict, settings: Settings) -> dict:
    _require_cognito_client(settings)

    try:
        response = httpx.post(
            _cognito_endpoint(settings),
            json=payload,
            headers={
                "Content-Type": "application/x-amz-json-1.1",
                "X-Amz-Target": f"AWSCognitoIdentityProviderService.{target}",
            },
            timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to reach Cognito service",
        ) from exc

    data = response.json() if response.content else {}
    if response.status_code >= 400:
        error_name, message = _extract_cognito_error(data)
        raise HTTPException(status_code=_map_cognito_http_status(error_name), detail=f"{error_name}: {message}")
    return data if isinstance(data, dict) else {}


def cognito_sign_up(email: str, password: str, settings: Settings) -> dict:
    payload = {
        "ClientId": settings.cognito_client_id,
        "Username": email,
        "Password": password,
        "UserAttributes": [{"Name": "email", "Value": email}],
    }
    secret_hash = _secret_hash(email, settings)
    if secret_hash:
        payload["SecretHash"] = secret_hash
    return _call_cognito("SignUp", payload, settings)


def cognito_confirm_sign_up(email: str, code: str, settings: Settings) -> dict:
    payload = {
        "ClientId": settings.cognito_client_id,
        "Username": email,
        "ConfirmationCode": code,
    }
    secret_hash = _secret_hash(email, settings)
    if secret_hash:
        payload["SecretHash"] = secret_hash
    return _call_cognito("ConfirmSignUp", payload, settings)


def cognito_resend_code(email: str, settings: Settings) -> dict:
    payload = {
        "ClientId": settings.cognito_client_id,
        "Username": email,
    }
    secret_hash = _secret_hash(email, settings)
    if secret_hash:
        payload["SecretHash"] = secret_hash
    return _call_cognito("ResendConfirmationCode", payload, settings)


def cognito_login(email: str, password: str, settings: Settings) -> dict:
    payload = {
        "ClientId": settings.cognito_client_id,
        "AuthFlow": "USER_PASSWORD_AUTH",
        "AuthParameters": {
            "USERNAME": email,
            "PASSWORD": password,
        },
    }
    secret_hash = _secret_hash(email, settings)
    if secret_hash:
        payload["AuthParameters"]["SECRET_HASH"] = secret_hash
    return _call_cognito("InitiateAuth", payload, settings)


def _generate_secure_password() -> str:
    """Generate a random password that meets Cognito complexity requirements."""
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    while True:
        pwd = "".join(secrets.choice(alphabet) for _ in range(24))
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
            and any(c in "!@#$%" for c in pwd)
        ):
            return pwd


def cognito_request_email_otp(email: str, settings: Settings) -> dict:
    """Auto-register new user if needed, then initiate EMAIL_OTP challenge."""
    local_part = email.split("@")[0]
    sign_up_payload: dict = {
        "ClientId": settings.cognito_client_id,
        "Username": email,
        "Password": _generate_secure_password(),
        "UserAttributes": [
            {"Name": "email", "Value": email},
            {"Name": "given_name", "Value": local_part},
            {"Name": "family_name", "Value": local_part},
        ],
    }
    secret_hash = _secret_hash(email, settings)
    if secret_hash:
        sign_up_payload["SecretHash"] = secret_hash
    try:
        _call_cognito("SignUp", sign_up_payload, settings)
    except HTTPException as exc:
        if "UsernameExistsException" not in str(exc.detail):
            raise

    auth_params: dict = {
        "USERNAME": email,
        "PREFERRED_CHALLENGE": "EMAIL_OTP",
    }
    if secret_hash:
        auth_params["SECRET_HASH"] = secret_hash
    data = _call_cognito(
        "InitiateAuth",
        {
            "ClientId": settings.cognito_client_id,
            "AuthFlow": "USER_AUTH",
            "AuthParameters": auth_params,
        },
        settings,
    )

    challenge_name = data.get("ChallengeName")
    session = data.get("Session")

    # USER_AUTH may return SELECT_CHALLENGE when the user has multiple auth options.
    # Respond immediately to select EMAIL_OTP so the caller gets the final OTP session.
    if challenge_name == "SELECT_CHALLENGE":
        select_responses: dict = {
            "USERNAME": email,
            "ANSWER": "EMAIL_OTP",
        }
        if secret_hash:
            select_responses["SECRET_HASH"] = secret_hash
        data = _call_cognito(
            "RespondToAuthChallenge",
            {
                "ClientId": settings.cognito_client_id,
                "ChallengeName": "SELECT_CHALLENGE",
                "Session": session,
                "ChallengeResponses": select_responses,
            },
            settings,
        )
        challenge_name = data.get("ChallengeName")
        session = data.get("Session")

    return {"session": session, "challenge_name": challenge_name}


def cognito_verify_email_otp(email: str, code: str, session: str, settings: Settings) -> dict:
    """Respond to EMAIL_OTP challenge and return Cognito tokens."""
    challenge_responses: dict = {
        "USERNAME": email,
        "EMAIL_OTP_CODE": code,
    }
    secret_hash = _secret_hash(email, settings)
    if secret_hash:
        challenge_responses["SECRET_HASH"] = secret_hash
    return _call_cognito(
        "RespondToAuthChallenge",
        {
            "ClientId": settings.cognito_client_id,
            "ChallengeName": "EMAIL_OTP",
            "Session": session,
            "ChallengeResponses": challenge_responses,
        },
        settings,
    )


def cognito_refresh(refresh_token: str, settings: Settings, email: str | None = None) -> dict:
    payload = {
        "ClientId": settings.cognito_client_id,
        "AuthFlow": "REFRESH_TOKEN_AUTH",
        "AuthParameters": {
            "REFRESH_TOKEN": refresh_token,
        },
    }
    if settings.cognito_client_secret:
        if not email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="email is required for refresh when Cognito client secret is enabled",
            )
        secret_hash = _secret_hash(email, settings)
        if secret_hash:
            payload["AuthParameters"]["SECRET_HASH"] = secret_hash
    return _call_cognito("InitiateAuth", payload, settings)
