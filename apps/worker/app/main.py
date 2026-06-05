import asyncio
import json
import uuid
from decimal import Decimal
from typing import Any

import redis.asyncio as redis

from app.broker_router import BrokerRouterClient
from app.config import get_settings
from app.engine import CopyOrderResult, CopyTradingEngine
from app.repository import CopyOrderRepository
from app.risk import CopyAccount, CopySettings, CopyTarget, MasterOrder


def _master_from_job(data: dict[str, Any]) -> MasterOrder:
    return MasterOrder(
        id=uuid.UUID(data["id"]),
        broker_order_id=data["broker_order_id"],
        exchange=data["exchange"],
        scrip_code=str(data["scrip_code"]),
        trading_symbol=data["trading_symbol"],
        transaction_type=data["transaction_type"],
        quantity=int(data["quantity"]),
        price=Decimal(str(data["price"])),
        trigger_price=Decimal(str(data.get("trigger_price", "0"))),
        order_type=data.get("order_type", "NORMAL"),
        product_type=data.get("product_type", "INVESTMENT"),
        request_type=data.get("request_type", "NEW"),
        raw_payload=data.get("raw_payload", {}),
    )


def _target_from_job(data: dict[str, Any]) -> CopyTarget:
    account_data = data["account"]
    settings_data = data.get("settings", {})
    return CopyTarget(
        account=CopyAccount(
            id=uuid.UUID(account_data["id"]),
            customer_id=account_data["customer_id"],
            login_id=account_data["login_id"],
            is_active=bool(account_data.get("is_active", True)),
            has_token=bool(account_data.get("has_token", False)),
            capital=Decimal(str(account_data["capital"])) if account_data.get("capital") is not None else None,
        ),
        settings=CopySettings(
            is_enabled=bool(settings_data.get("is_enabled", True)),
            sizing_mode=settings_data.get("sizing_mode", "SAME_QTY"),
            multiplier=Decimal(str(settings_data.get("multiplier", "1"))),
            fixed_qty=settings_data.get("fixed_qty"),
            capital_percent=Decimal(str(settings_data["capital_percent"]))
            if settings_data.get("capital_percent") is not None
            else None,
            max_qty=settings_data.get("max_qty"),
            max_order_value=Decimal(str(settings_data["max_order_value"]))
            if settings_data.get("max_order_value") is not None
            else None,
            allowed_symbols=settings_data.get("allowed_symbols", []),
            blocked_symbols=settings_data.get("blocked_symbols", []),
            allowed_transaction_types=settings_data.get("allowed_transaction_types", ["B", "S"]),
            allowed_product_types=settings_data.get("allowed_product_types", []),
            product_type_map=settings_data.get("product_type_map", {}),
            price_mode=settings_data.get("price_mode", "SAME_PRICE"),
            max_slippage_percent=Decimal(str(settings_data["max_slippage_percent"]))
            if settings_data.get("max_slippage_percent") is not None
            else None,
            is_auto_squareoff_enabled=bool(settings_data.get("is_auto_squareoff_enabled", False)),
        ),
    )


async def handle_job(job: dict[str, Any]) -> list[CopyOrderResult]:
    settings = get_settings()
    master_order = _master_from_job(job["master_order"])
    targets = [_target_from_job(target) for target in job.get("targets", [])]
    repository = CopyOrderRepository()
    broker_router = BrokerRouterClient()

    async def save(result: CopyOrderResult, request_payload: dict[str, Any], response_payload: dict[str, Any]) -> None:
        await repository.save(
            master_order_id=master_order.id,
            result=result,
            request_payload=request_payload,
            response_payload=response_payload,
        )

    engine = CopyTradingEngine(
        place_order=broker_router.place_order,
        order_exists=repository.exists,
        save_copy_order=save,
        max_retries=settings.max_copy_retries,
    )
    return await engine.process_master_order(
        master_order,
        targets,
        enforce_market_hours=bool(job.get("enforce_market_hours", True)),
    )


async def run_forever() -> None:
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            item = await client.brpop(settings.copy_job_queue, timeout=5)
            if not item:
                continue
            _, raw = item
            await handle_job(json.loads(raw))
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(run_forever())

