"""Application settings loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration contract for the backend MVP."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    app_name: str = Field(default="Eco-Health Agentic Dietitian API", alias="APP_NAME")
    api_v1_str: str = Field(default="/api/v1", alias="API_V1_STR")
    env: Literal["development", "staging", "production"] = Field(default="development", alias="ENV")
    debug: bool = Field(default=True, alias="DEBUG")

    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    adk_enabled: bool = Field(default=False, alias="ADK_ENABLED")
    adk_model: str = Field(default="gemini-2.0-flash", alias="ADK_MODEL")

    cognito_region: str = Field(default="us-east-1", alias="COGNITO_REGION")
    cognito_user_pool_id: str = Field(default="", alias="COGNITO_USER_POOL_ID")
    cognito_client_id: str = Field(default="", alias="COGNITO_CLIENT_ID")
    cognito_client_secret: str = Field(default="", alias="COGNITO_CLIENT_SECRET")
    cognito_issuer: str = Field(default="", alias="COGNITO_ISSUER")
    cognito_user_pool_arn: str = Field(default="", alias="COGNITO_USER_POOL_ARN")
    cognito_jwks_url: str = Field(default="", alias="COGNITO_JWKS_URL")

    recipe_api_base_url: str = Field(default="", alias="RECIPE_API_BASE_URL")
    recipe_api_key: str = Field(default="", alias="RECIPE_API_KEY")

    database_url: str = Field(default="", alias="DATABASE_URL")
    redis_url: str = Field(default="", alias="REDIS_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid repeated environment parsing."""

    return Settings()
