from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(
        "postgresql+asyncpg://copytrader:copytrader_password@postgres:5432/copytrading",
        alias="DATABASE_URL",
    )
    redis_url: str = Field("redis://redis:6379/0", alias="REDIS_URL")
    broker_router_url: str = Field("http://broker-router:8001", alias="BROKER_ROUTER_URL")
    paper_trading_mode: bool = Field(True, alias="PAPER_TRADING_MODE")
    copy_job_queue: str = "copy_jobs"
    max_copy_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()

