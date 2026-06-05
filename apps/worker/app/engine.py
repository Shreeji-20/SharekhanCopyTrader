import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.risk import CopyTarget, MasterOrder, RiskRejected, copy_order_payload, idempotency_key, validate_risk


@dataclass(frozen=True)
class CopyOrderResult:
    copy_account_id: uuid.UUID
    status: str
    idempotency_key: str
    calculated_quantity: int = 0
    broker_order_id: str | None = None
    error_message: str | None = None
    retry_count: int = 0


PlaceOrder = Callable[[uuid.UUID, dict[str, Any]], Awaitable[dict[str, Any]]]
OrderExists = Callable[[str], Awaitable[bool]]
SaveCopyOrder = Callable[[CopyOrderResult, dict[str, Any], dict[str, Any]], Awaitable[None]]


class CopyTradingEngine:
    def __init__(
        self,
        *,
        place_order: PlaceOrder,
        order_exists: OrderExists,
        save_copy_order: SaveCopyOrder,
        max_retries: int = 3,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self.place_order = place_order
        self.order_exists = order_exists
        self.save_copy_order = save_copy_order
        self.max_retries = max_retries
        self.sleep = sleep

    async def process_master_order(
        self,
        master_order: MasterOrder,
        targets: list[CopyTarget],
        *,
        enforce_market_hours: bool = True,
    ) -> list[CopyOrderResult]:
        results: list[CopyOrderResult] = []
        for target in targets:
            key = idempotency_key(master_order.id, target.account.id, master_order.request_type)
            if await self.order_exists(key):
                result = CopyOrderResult(target.account.id, "SKIPPED", key, error_message="duplicate idempotency key")
                await self.save_copy_order(result, {}, {})
                results.append(result)
                continue

            try:
                quantity = validate_risk(master_order, target, enforce_market_hours=enforce_market_hours)
                request_payload = copy_order_payload(master_order, target, quantity)
            except RiskRejected as exc:
                result = CopyOrderResult(target.account.id, "SKIPPED", key, error_message=exc.reason)
                await self.save_copy_order(result, {}, {})
                results.append(result)
                continue

            result = await self._send_with_retry(target, key, quantity, request_payload)
            await self.save_copy_order(result, request_payload, {"broker_order_id": result.broker_order_id})
            results.append(result)
        return results

    async def _send_with_retry(
        self,
        target: CopyTarget,
        key: str,
        quantity: int,
        request_payload: dict[str, Any],
    ) -> CopyOrderResult:
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.place_order(target.account.id, request_payload)
                normalized = response.get("normalized") or response.get("data") or response
                broker_order_id = normalized.get("broker_order_id") or normalized.get("orderId")
                return CopyOrderResult(
                    copy_account_id=target.account.id,
                    status="SUCCESS",
                    idempotency_key=key,
                    calculated_quantity=quantity,
                    broker_order_id=broker_order_id,
                    retry_count=attempt,
                )
            except Exception as exc:
                last_error = str(exc)
                if attempt < self.max_retries:
                    await self.sleep(2**attempt)
        return CopyOrderResult(
            copy_account_id=target.account.id,
            status="FAILED",
            idempotency_key=key,
            calculated_quantity=quantity,
            error_message=last_error or "unknown broker error",
            retry_count=self.max_retries,
        )


def decimal_from(value: Any, default: str = "0") -> Decimal:
    return Decimal(str(value if value is not None else default))

