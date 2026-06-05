import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Column, DateTime, Integer, MetaData, Numeric, String, Table, Text, insert, select
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.engine import CopyOrderResult

metadata = MetaData()

copy_orders = Table(
    "copy_orders",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column("master_order_id", UUID(as_uuid=True), nullable=False),
    Column("copy_account_id", UUID(as_uuid=True), nullable=False),
    Column("broker_order_id", String(120), nullable=True),
    Column("status", String(40), nullable=False),
    Column("calculated_quantity", Integer, nullable=False),
    Column("calculated_price", Numeric(18, 4), nullable=False),
    Column("request_payload", JSONB, nullable=False),
    Column("response_payload", JSONB, nullable=False),
    Column("error_message", Text, nullable=True),
    Column("retry_count", Integer, nullable=False),
    Column("idempotency_key", String(255), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class CopyOrderRepository:
    async def exists(self, idempotency_key: str) -> bool:
        async with AsyncSessionLocal() as session:
            value = await session.scalar(
                select(copy_orders.c.id).where(copy_orders.c.idempotency_key == idempotency_key).limit(1)
            )
            return value is not None

    async def save(
        self,
        *,
        master_order_id: uuid.UUID,
        result: CopyOrderResult,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc)
        price = Decimal(str(request_payload.get("price", "0")))
        async with AsyncSessionLocal() as session:
            await session.execute(
                insert(copy_orders).values(
                    id=uuid.uuid4(),
                    master_order_id=master_order_id,
                    copy_account_id=result.copy_account_id,
                    broker_order_id=result.broker_order_id,
                    status=result.status,
                    calculated_quantity=result.calculated_quantity,
                    calculated_price=price,
                    request_payload=request_payload,
                    response_payload=response_payload,
                    error_message=result.error_message,
                    retry_count=result.retry_count,
                    idempotency_key=result.idempotency_key,
                    created_at=now,
                    updated_at=now,
                )
            )
            await session.commit()

