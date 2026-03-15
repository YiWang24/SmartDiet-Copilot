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
    env: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENV"
    )
    debug: bool = Field(default=True, alias="DEBUG")
    cors_allowed_origins: str = Field(
        default="http://localhost:3000", alias="CORS_ALLOWED_ORIGINS"
    )

    # Agent + model settings
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    railtracks_enabled: bool = Field(default=False, alias="RAILTRACKS_ENABLED")
    railtracks_base_url: str = Field(default="", alias="RAILTRACKS_BASE_URL")
    railtracks_model: str = Field(default="gemini-2.5-pro", alias="RAILTRACKS_MODEL")
    gemini_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_MODEL")
    gemini_vision_model: str = Field(default="gemini-2.5-pro", alias="GEMINI_VISION_MODEL")
    gemini_embedding_model: str = Field(
        default="gemini-embedding-001", alias="GEMINI_EMBEDDING_MODEL"
    )
    vector_store_mode: Literal["memory", "file"] = Field(
        default="memory", alias="VECTOR_STORE_MODE"
    )
    chroma_persist_dir: str = Field(default="./chroma_db", alias="CHROMA_PERSIST_DIR")
    chroma_collection_name: str = Field(
        default="eco_health", alias="CHROMA_COLLECTION_NAME"
    )
    vector_snapshot_path: str = Field(
        default="./data/vector_snapshot.json", alias="VECTOR_SNAPSHOT_PATH"
    )

    cognito_region: str = Field(default="us-east-1", alias="COGNITO_REGION")
    cognito_user_pool_id: str = Field(default="", alias="COGNITO_USER_POOL_ID")
    cognito_client_id: str = Field(default="", alias="COGNITO_CLIENT_ID")
    cognito_client_secret: str = Field(default="", alias="COGNITO_CLIENT_SECRET")
    cognito_issuer: str = Field(default="", alias="COGNITO_ISSUER")
    cognito_user_pool_arn: str = Field(default="", alias="COGNITO_USER_POOL_ARN")
    cognito_jwks_url: str = Field(default="", alias="COGNITO_JWKS_URL")
    cognito_jwks_json: str = Field(default="", alias="COGNITO_JWKS_JSON")
    cognito_jwks_path: str = Field(default="", alias="COGNITO_JWKS_PATH")
    auth_bypass_enabled: bool = Field(default=False, alias="AUTH_BYPASS_ENABLED")

    recipe_api_base_url: str = Field(default="", alias="RECIPE_API_BASE_URL")
    recipe_api_key: str = Field(default="", alias="RECIPE_API_KEY")

    database_url: str = Field(
        default="",
        alias="DATABASE_URL",
    )
    sqlite_mode: Literal["memory", "file"] = Field(
        default="memory", alias="SQLITE_MODE"
    )
    sqlite_snapshot_path: str = Field(
        default="./data/eco_health.sqlite3", alias="SQLITE_SNAPSHOT_PATH"
    )
    sqlite_auto_snapshot: bool = Field(default=True, alias="SQLITE_AUTO_SNAPSHOT")
    redis_url: str = Field(default="", alias="REDIS_URL")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings to avoid repeated environment parsing."""

    return Settings()
