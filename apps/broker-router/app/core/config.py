from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = Field("development", alias="ENVIRONMENT")
    database_url: str = Field(
        "postgresql+asyncpg://copytrader:copytrader_password@postgres:5432/copytrading",
        alias="DATABASE_URL",
    )
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")
    app_secret_key: str = Field("32_byte_base64_key_here", alias="APP_SECRET_KEY")
    sharekhan_base_url: str = Field("https://api.sharekhan.com", alias="SHAREKHAN_BASE_URL")
    sharekhan_login_url: str = Field(
        "https://api.sharekhan.com/skapi/auth/login.html",
        alias="SHAREKHAN_LOGIN_URL",
    )
    sharekhan_ws_url: str = Field("wss://stream.sharekhan.com/skstream/api/stream", alias="SHAREKHAN_WS_URL")
    sharekhan_version_id: str = Field("1005", alias="SHAREKHAN_VERSION_ID")
    paper_trading_mode: bool = Field(True, alias="PAPER_TRADING_MODE")
    broker_rate_limit_per_minute: int = Field(120, alias="BROKER_RATE_LIMIT_PER_MINUTE")

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        if self.environment.lower() != "production":
            return self
        if self.app_secret_key in {"", "32_byte_base64_key_here"}:
            raise ValueError("APP_SECRET_KEY must be set to a strong value in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
