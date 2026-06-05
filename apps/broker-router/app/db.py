import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.security import decrypt_secret, encrypt_secret

metadata = MetaData()

broker_accounts = Table(
    "broker_accounts",
    metadata,
    # Only the columns broker-router needs are declared here.
    # SQLAlchemy Core can query this partial table definition safely.
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("customer_id", String(80)),
    Column("login_id", String(120)),
    Column("api_key", Text),
    Column("secret_key", Text),
    Column("vendor_key", Text),
    Column("proxy_scheme", String(10)),
    Column("proxy_host", Text),
    Column("proxy_port", Integer),
    Column("proxy_username", Text),
    Column("proxy_password", Text),
    Column("sharekhan_login_state", String(32)),
    Column("request_token", Text),
    Column("access_token", Text),
    Column("refresh_token", Text),
    Column("token_expires_at", DateTime(timezone=True)),
    Column("last_connected_at", DateTime(timezone=True)),
)

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


@dataclass(frozen=True)
class SharekhanAccount:
    id: uuid.UUID
    customer_id: str | None
    login_id: str | None
    api_key: str
    secret_key: str
    vendor_key: str | None
    proxy_scheme: str | None
    proxy_host: str | None
    proxy_port: int | None
    proxy_username: str | None
    proxy_password: str | None
    sharekhan_login_state: str | None
    request_token: str | None
    access_token: str | None
    refresh_token: str | None
    token_expires_at: datetime | None


def _decrypt_account_secret(value: str | None, field: str, *, required: bool = True) -> str | None:
    if value is None:
        return None
    try:
        return decrypt_secret(value)
    except Exception as exc:
        if not required:
            return None
        raise ValueError(
            f"Stored Sharekhan {field} cannot be decrypted. Re-save the account credentials with the current app secret."
        ) from exc


async def load_account(db: AsyncSession, account_id: uuid.UUID) -> SharekhanAccount:
    row = (await db.execute(select(broker_accounts).where(broker_accounts.c.id == account_id))).mappings().first()
    if row is None:
        raise LookupError("Broker account not found")
    return SharekhanAccount(
        id=row["id"],
        customer_id=row["customer_id"],
        login_id=row["login_id"],
        api_key=_decrypt_account_secret(row["api_key"], "API key") or "",
        secret_key=_decrypt_account_secret(row["secret_key"], "Secure Key") or "",
        vendor_key=_decrypt_account_secret(row["vendor_key"], "vendor key"),
        proxy_scheme=row["proxy_scheme"],
        proxy_host=_decrypt_account_secret(row["proxy_host"], "proxy host"),
        proxy_port=row["proxy_port"],
        proxy_username=_decrypt_account_secret(row["proxy_username"], "proxy username"),
        proxy_password=_decrypt_account_secret(row["proxy_password"], "proxy password"),
        sharekhan_login_state=row["sharekhan_login_state"],
        request_token=_decrypt_account_secret(row["request_token"], "request token", required=False),
        access_token=_decrypt_account_secret(row["access_token"], "access token", required=False),
        refresh_token=_decrypt_account_secret(row["refresh_token"], "refresh token", required=False),
        token_expires_at=row["token_expires_at"],
    )


async def store_tokens(
    db: AsyncSession,
    account_id: uuid.UUID,
    *,
    access_token: str | None,
    refresh_token: str | None = None,
    token_expires_at: datetime | None = None,
    customer_id: str | None = None,
    login_id: str | None = None,
) -> None:
    values = {
        "sharekhan_login_state": None,
        "access_token": encrypt_secret(access_token),
        "refresh_token": encrypt_secret(refresh_token),
        "token_expires_at": token_expires_at,
        "last_connected_at": datetime.now(timezone.utc),
    }
    if customer_id:
        values["customer_id"] = customer_id
    if login_id:
        values["login_id"] = login_id
    await db.execute(
        update(broker_accounts)
        .where(broker_accounts.c.id == account_id)
        .values(**values)
    )
    await db.commit()
