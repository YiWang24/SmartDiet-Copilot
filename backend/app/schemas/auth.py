"""Authentication schema types."""

from pydantic import BaseModel, Field, field_validator


class AuthContext(BaseModel):
    user_id: str
    email: str | None = None


class CognitoRegisterRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized:
            raise ValueError("email must be a valid address")
        return normalized


class CognitoRegisterResponse(BaseModel):
    email: str
    user_sub: str | None = None
    user_confirmed: bool = False
    code_delivery_medium: str | None = None
    code_destination: str | None = None


class CognitoConfirmRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    code: str = Field(..., min_length=1, max_length=20)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip()


class CognitoResendCodeRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class CognitoLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    password: str = Field(..., min_length=8, max_length=256)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class OtpRequestSchema(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class OtpVerifyRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=320)
    code: str = Field(..., min_length=6, max_length=8)
    session: str = Field(..., min_length=10)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip()


class CognitoRefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=20)
    email: str | None = Field(default=None, min_length=5, max_length=320)

    @field_validator("refresh_token")
    @classmethod
    def normalize_refresh_token(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip().lower()


class CognitoTokenResponse(BaseModel):
    id_token: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str | None = None
    expires_in: int | None = None
