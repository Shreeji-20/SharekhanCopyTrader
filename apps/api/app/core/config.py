from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field("development", alias="ENVIRONMENT")
    database_url: str = Field(
        "postgresql+asyncpg://copytrader:copytrader_password@postgres:5432/copytrading",
        alias="DATABASE_URL",
    )
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")
    jwt_secret: str = Field("change_me", alias="JWT_SECRET")
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(1440, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    app_secret_key: str = Field("32_byte_base64_key_here", alias="APP_SECRET_KEY")
    broker_router_url: str = Field("http://broker-router:8001", alias="BROKER_ROUTER_URL")
    paper_trading_mode: bool = Field(True, alias="PAPER_TRADING_MODE")
    copy_trading_dry_run: bool = Field(True, alias="COPY_TRADING_DRY_RUN")
    script_master_cache_ttl_hours: int = Field(24, alias="SCRIPT_MASTER_CACHE_TTL_HOURS")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"],
        alias="CORS_ORIGINS",
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, str) and value and not value.lstrip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment.lower() != "production":
            return self
        if self.jwt_secret in {"", "change_me"}:
            raise ValueError("JWT_SECRET must be set to a strong value in production")
        if self.app_secret_key in {"", "32_byte_base64_key_here"}:
            raise ValueError("APP_SECRET_KEY must be set to a strong value in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
