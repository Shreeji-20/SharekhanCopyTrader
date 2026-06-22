import asyncio
import contextlib
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from time import perf_counter
from typing import Any

import redis.asyncio as redis
from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.models import (
    BrokerAccount,
    CopiedTradeOrder,
    CopiedTradeOrderStatus,
    CopyGroup,
    CopyGroupMember,
    CopySession,
    CopySessionStatus,
    CopySetting,
    MasterTradeEvent,
    PriceMode,
    Position,
    SizingMode,
)
from app.services.broker_router import BrokerRouterClient
from app.services.script_master import AMBIGUOUS, ScriptMasterLookup, script_master_service

logger = logging.getLogger(__name__)
IST = timezone(timedelta(hours=5, minutes=30))


class CopySkip(Exception):
    pass


@dataclass(frozen=True)
class NormalizedTradeEvent:
    external_trade_id: str | None
    external_order_id: str | None
    symbol: str
    exchange: str
    side: str
    quantity: int
    price: Decimal
    order_type: str
    product_type: str
    raw_payload: dict[str, Any]
    event_time: datetime | None
    duplicate_hash: str
    scrip_code: int | None = None
    trigger_price: Decimal = Decimal("0")
    disclosed_qty: int = 0
    instrument_type: str | None = None
    option_type: str | None = None
    strike_price: Decimal | None = None
    expiry: str | None = None
    segment: str | None = None
    isin: str | None = None
    lot_size: int | None = None
    scrip_code_resolution_status: str | None = None
    scrip_code_resolution_message: str | None = None


@dataclass(frozen=True)
class CopyRiskUsage:
    trades_today: int = 0
    current_daily_loss: Decimal = Decimal("0")


@dataclass(frozen=True)
class CopyTargetPlan:
    member_id: uuid.UUID
    copy_group_id: uuid.UUID
    copy_group_name: str
    setting: CopySetting
    copy_account: BrokerAccount


@dataclass(frozen=True)
class CachedCopyTargets:
    master_account_id: uuid.UUID
    group_ids: tuple[str, ...]
    loaded_at: float
    targets: tuple[CopyTargetPlan, ...]


@dataclass(frozen=True)
class CopyTargetResult:
    target: CopyTargetPlan
    order_status: CopiedTradeOrderStatus
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    child_order_id: str | None
    error_message: str | None
    duration_ms: float
    dispatch_started_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    start_offset_ms: float | None = None
    dispatch_gap_ms: float | None = None


@dataclass(frozen=True)
class PreparedCopyOrder:
    target: CopyTargetPlan
    request_payload: dict[str, Any]


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    lower_map = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = lower_map.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def _string_or_none(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text or text == "0":
        return None
    return text


def _upper(value: Any, default: str = "") -> str:
    text = str(value or default).strip().upper()
    return text or default


def _int_value(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, ValueError):
        return default


def _decimal_value(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    if value in (None, ""):
        return default
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError):
        return default


def _decimal_json(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01"), rounding=ROUND_DOWN), "f")


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_event_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=IST)
        return parsed
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _normalize_order_type(value: Any) -> str:
    order_type = _upper(value, "NORMAL")
    if order_type in {"NOR", "NORMAL"}:
        return "NORMAL"
    return order_type


def _normalize_side(value: Any) -> str:
    side = _upper(value, "")
    if side in {"B", "BUY"}:
        return "B"
    if side in {"S", "SELL"}:
        return "S"
    return side


def _scrip_code(data: dict[str, Any]) -> int | None:
    value = _first(data, "ScripCode", "scripCode", "ScripToken", "Token", "ExchangeScripCode")
    parsed = _int_value(value, 0)
    return parsed or None


def normalize_sharekhan_ack(payload: Any) -> NormalizedTradeEvent | None:
    if not isinstance(payload, dict):
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    data_keys = {str(key).lower() for key in data}
    if not any(key in data_keys for key in ("sharekhanorderid", "exchangeorderid", "ackstate", "tradeid")):
        return None

    trade_qty = _int_value(_first(data, "TradeQty", "tradeQty"), 0)
    ack_state = _upper(_first(data, "AckState", "ackState"), "")
    compact_ack_state = "".join(ch for ch in ack_state if ch.isalnum())
    is_fill_state = any(marker in ack_state for marker in ("TRADE", "EXEC", "FILL"))
    is_rejected_state = any(marker in compact_ack_state for marker in ("REJECT", "CANCEL", "FAIL", "ERROR"))
    is_new_order_state = "NEWORDER" in compact_ack_state and not is_rejected_state
    if trade_qty <= 0 and not is_fill_state and not is_new_order_state:
        return None

    quantity = trade_qty or _int_value(_first(data, "OrderQty", "orderQty", "Qty"), 0)
    symbol = _upper(_first(data, "TradingSymbol", "tradingSymbol", "Symbol"), "")
    side = _normalize_side(_first(data, "BuySellString", "transactionType", "Side"))
    exchange = _upper(_first(data, "Exchange", "exchange", "exchangeCode"), "")
    price = _decimal_value(_first(data, "TradePrice", "tradePrice"), Decimal("0"))
    if price <= 0:
        price = _decimal_value(_first(data, "OrderPrice", "orderPrice", "Price"), Decimal("0"))
    if quantity <= 0 or not symbol or side not in {"B", "S"} or not exchange:
        return None

    event_time = _parse_event_time(_first(data, "ExchangeDateTime", "exchangeDateTime", "TradeTime"))
    event_time = event_time or _parse_event_time(payload.get("timestamp"))
    external_trade_id = _string_or_none(_first(data, "TradeID", "tradeId"))
    external_order_id = _string_or_none(_first(data, "SharekhanOrderID", "ExchangeOrderID", "orderId"))
    if external_order_id:
        identity = {"order": external_order_id, "symbol": symbol, "side": side}
    else:
        identity = {
            "trade": external_trade_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "price": str(price),
            "event_time": event_time.isoformat() if event_time else None,
        }
    duplicate_hash = hashlib.sha256(json.dumps(identity, sort_keys=True).encode("utf-8")).hexdigest()

    return NormalizedTradeEvent(
        external_trade_id=external_trade_id,
        external_order_id=external_order_id,
        symbol=symbol,
        exchange=exchange,
        side=side,
        quantity=quantity,
        price=price,
        order_type=_normalize_order_type(_first(data, "OrderType", "orderType")),
        product_type=_upper(_first(data, "ProductType", "productType"), "INVESTMENT"),
        raw_payload=payload,
        event_time=event_time,
        duplicate_hash=duplicate_hash,
        scrip_code=_scrip_code(data),
        trigger_price=_decimal_value(_first(data, "TriggerPrice", "triggerPrice"), Decimal("0")),
        disclosed_qty=_int_value(_first(data, "DisclosedQty", "disclosedQty"), 0),
        instrument_type=_string_or_none(_first(data, "InstrumentType", "instrumentType", "InsType", "insType")),
        option_type=_string_or_none(_first(data, "OptionType", "optionType", "CPType", "cpType")),
        strike_price=_decimal_value(_first(data, "StrikePrice", "strikePrice", "Strike", "strike"), Decimal("0")) or None,
        expiry=_string_or_none(_first(data, "Expiry", "expiry", "ExpiryDate", "expiryDate")),
        segment=_string_or_none(_first(data, "SegmentCode", "segmentCode", "Segment", "segment")),
        isin=_string_or_none(_first(data, "ISIN", "isin", "IsinCode", "isinCode")),
        lot_size=_int_value(_first(data, "LotSize", "lotSize", "MarketLot", "marketLot"), 0) or None,
    )


def calculate_copy_quantity(master_quantity: int, setting: CopySetting) -> int:
    if setting.sizing_mode == SizingMode.SAME_QTY:
        quantity = master_quantity
    elif setting.sizing_mode == SizingMode.MULTIPLIER:
        quantity = int((Decimal(master_quantity) * setting.multiplier).to_integral_value(rounding=ROUND_DOWN))
    elif setting.sizing_mode == SizingMode.FIXED_QTY:
        quantity = setting.fixed_qty or 0
    elif setting.sizing_mode == SizingMode.PERCENT_CAPITAL:
        raise CopySkip("PERCENT_CAPITAL sizing requires synced account capital and is not enabled for live WebSocket copying yet.")
    else:
        quantity = 0
    if quantity <= 0:
        raise CopySkip("Calculated quantity is zero.")
    min_qty = getattr(setting, "min_qty", None)
    max_qty = getattr(setting, "max_qty", None)
    if min_qty and quantity < min_qty:
        raise CopySkip("Calculated quantity is below min_qty.")
    if max_qty and quantity > max_qty:
        raise CopySkip("Calculated quantity exceeds max_qty.")
    return quantity


def calculate_copy_price(event: NormalizedTradeEvent, setting: CopySetting) -> Decimal:
    if setting.price_mode == PriceMode.MARKET:
        return Decimal("0")
    if setting.price_mode == PriceMode.LIMIT_WITH_SLIPPAGE:
        slippage = (setting.max_slippage_percent or Decimal("0")) / Decimal("100")
        multiplier = Decimal("1") + slippage if event.side == "B" else Decimal("1") - slippage
        return (event.price * multiplier).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    return event.price.quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def _normalized_set(values: list[str] | None) -> set[str]:
    return {str(value).strip().upper() for value in values or [] if str(value).strip()}


def build_sharekhan_copy_order_payload(
    event: NormalizedTradeEvent,
    setting: CopySetting,
    copy_account: BrokerAccount,
    risk_usage: CopyRiskUsage | None = None,
) -> dict[str, Any]:
    if not copy_account.is_active:
        raise CopySkip("Copy account is inactive.")
    missing = [
        label
        for label, value in (
            ("api_key", copy_account.api_key),
            ("secret_key", copy_account.secret_key),
            ("customer_id", copy_account.customer_id),
            ("login_id", copy_account.login_id),
            ("access_token", copy_account.access_token),
        )
        if not value
    ]
    if missing:
        raise CopySkip(f"Copy account is missing required fields: {', '.join(missing)}.")
    if not setting.is_enabled:
        raise CopySkip("Copy settings are disabled.")
    allowed_symbols = _normalized_set(setting.allowed_symbols)
    blocked_symbols = _normalized_set(setting.blocked_symbols)
    allowed_transaction_types = _normalized_set(setting.allowed_transaction_types)
    if allowed_symbols and event.symbol not in allowed_symbols:
        raise CopySkip(f"{event.symbol} is not in allowed symbols.")
    if event.symbol in blocked_symbols:
        raise CopySkip(f"{event.symbol} is blocked.")
    if allowed_transaction_types and event.side not in allowed_transaction_types:
        raise CopySkip(f"{event.side} is not an allowed transaction type.")
    if event.scrip_code is None:
        if event.scrip_code_resolution_status == AMBIGUOUS:
            raise CopySkip(event.scrip_code_resolution_message or "multiple Script Master matches found.")
        raise CopySkip(event.scrip_code_resolution_message or "scripCode missing and could not be resolved from Script Master.")

    product_map = {str(key).upper(): str(value).upper() for key, value in (setting.product_type_map or {}).items()}
    product_type = product_map.get(event.product_type.upper(), event.product_type.upper())
    allowed_product_types = _normalized_set(setting.allowed_product_types)
    if allowed_product_types and product_type not in allowed_product_types:
        raise CopySkip(f"{product_type} is not an allowed product type.")

    quantity = calculate_copy_quantity(event.quantity, setting)
    price = calculate_copy_price(event, setting)
    value_price = event.price if price == 0 else price
    if setting.max_order_value and value_price * quantity > setting.max_order_value:
        raise CopySkip("Calculated order value exceeds max_order_value.")
    risk_usage = risk_usage or CopyRiskUsage()
    max_trades_per_day = getattr(setting, "max_trades_per_day", None)
    max_daily_loss = getattr(setting, "max_daily_loss", None)
    if max_trades_per_day and risk_usage.trades_today >= max_trades_per_day:
        raise CopySkip("max_trades_per_day has already been reached for this copy account in this group.")
    if max_daily_loss and risk_usage.current_daily_loss >= max_daily_loss:
        raise CopySkip("max_daily_loss has already been reached for this copy account.")

    payload: dict[str, Any] = {
        "customerId": copy_account.customer_id,
        "scripCode": event.scrip_code,
        "tradingSymbol": event.symbol,
        "exchange": event.exchange,
        "transactionType": event.side,
        "quantity": quantity,
        "disclosedQty": event.disclosed_qty,
        "price": _decimal_json(price),
        "triggerPrice": _decimal_json(event.trigger_price),
        "rmsCode": "ANY",
        "afterHour": "N",
        "orderType": event.order_type,
        "channelUser": copy_account.login_id,
        "validity": "GFD",
        "requestType": "NEW",
        "productType": product_type,
    }
    optional_fields = {
        "instrumentType": event.instrument_type,
        "optionType": event.option_type,
        "expiry": event.expiry,
        "strikePrice": _decimal_json(event.strike_price) if event.strike_price else None,
    }
    payload.update({key: value for key, value in optional_fields.items() if value})
    return payload


def extract_child_order_id(response: dict[str, Any]) -> str | None:
    candidates: list[Any] = []
    if isinstance(response, dict):
        candidates.extend(response.get(key) for key in ("orderId", "orderID", "SharekhanOrderID", "broker_order_id"))
        data = response.get("data")
        if isinstance(data, dict):
            candidates.extend(data.get(key) for key in ("orderId", "orderID", "SharekhanOrderID", "brokerOrderId"))
    for candidate in candidates:
        text = _string_or_none(candidate)
        if text:
            return text
    return None


class LiveCopyManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._target_cache: dict[str, CachedCopyTargets] = {}
        self._target_cache_ttl_seconds = 15.0
        self._lock = asyncio.Lock()

    def invalidate_session_targets(self, session_id: uuid.UUID | str) -> None:
        self._target_cache.pop(str(session_id), None)

    def invalidate_master_targets(self, master_account_id: uuid.UUID | str) -> None:
        master_key = str(master_account_id)
        stale_session_ids = [
            session_id
            for session_id, cached in self._target_cache.items()
            if str(cached.master_account_id) == master_key
        ]
        for session_id in stale_session_ids:
            self._target_cache.pop(session_id, None)

    async def preload_session_targets(self, session_id: uuid.UUID) -> None:
        async with AsyncSessionLocal() as db:
            session = await db.get(CopySession, session_id)
            if session and session.status in {CopySessionStatus.RUNNING, CopySessionStatus.PAUSED}:
                await self._load_copy_targets(db, session, {})

    async def start_session_task(self, session_id: uuid.UUID) -> None:
        key = str(session_id)
        async with self._lock:
            task = self._tasks.get(key)
            if task and not task.done():
                return
            self._tasks[key] = asyncio.create_task(self._run_session(key), name=f"live-copy-{key}")

    async def stop_session_task(self, session_id: uuid.UUID) -> None:
        key = str(session_id)
        self.invalidate_session_targets(key)
        async with self._lock:
            task = self._tasks.pop(key, None)
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def resume_running_sessions(self) -> None:
        async with AsyncSessionLocal() as db:
            sessions = (
                await db.scalars(select(CopySession).where(CopySession.status == CopySessionStatus.RUNNING))
            ).all()
            for session in sessions:
                try:
                    await BrokerRouterClient().ws_connect(session.master_account_id)
                except Exception as exc:
                    logger.exception("Could not reconnect Sharekhan stream for running live copy session")
                    session.status = CopySessionStatus.ERROR
                    session.last_error = f"Could not reconnect Sharekhan stream on API startup: {exc}"
                    continue
                await self.start_session_task(session.id)
            await db.commit()

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()
            self._target_cache.clear()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _run_session(self, session_id: str) -> None:
        settings = get_settings()
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe("sharekhan:ticks")
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    if await self._session_finished(session_id):
                        return
                    continue
                data = message.get("data")
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except ValueError:
                        continue
                if isinstance(data, dict):
                    await self.process_redis_message(uuid.UUID(session_id), data)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Live copy session listener crashed", extra={"session_id": session_id})
            await self._mark_session_error(session_id, "Live copy session listener crashed. Check API logs.")
        finally:
            with contextlib.suppress(Exception):
                await pubsub.unsubscribe("sharekhan:ticks")
            with contextlib.suppress(Exception):
                await pubsub.aclose()
            await redis_client.aclose()

    async def _session_finished(self, session_id: str) -> bool:
        async with AsyncSessionLocal() as db:
            session = await db.get(CopySession, uuid.UUID(session_id))
            return session is None or session.status in {CopySessionStatus.STOPPED, CopySessionStatus.ERROR}

    async def _mark_session_error(self, session_id: str, error: str) -> None:
        self.invalidate_session_targets(session_id)
        async with AsyncSessionLocal() as db:
            session = await db.get(CopySession, uuid.UUID(session_id))
            if session:
                session.status = CopySessionStatus.ERROR
                session.last_error = error
                await db.commit()

    async def process_redis_message(self, session_id: uuid.UUID, message: dict[str, Any]) -> MasterTradeEvent | None:
        received_perf = perf_counter()
        logger.info(
            "live_copy.websocket_event_received",
            extra={
                "session_id": str(session_id),
                "account_id": str(message.get("account_id")),
                "message_type": message.get("type"),
                "received_at": _utc_timestamp(),
            },
        )
        async with AsyncSessionLocal() as db:
            session = await db.get(CopySession, session_id)
            if not session or session.status != CopySessionStatus.RUNNING:
                return None
            if str(message.get("account_id")) != str(session.master_account_id):
                return None
            if message.get("type") not in {None, "ack", "feed"}:
                return None
            parse_started = perf_counter()
            normalized = normalize_sharekhan_ack(message.get("payload"))
            parse_ms = (perf_counter() - parse_started) * 1000
            if normalized is None:
                return None
            return await self.copy_normalized_event(
                db,
                session,
                normalized,
                timings={"_received_perf": received_perf, "parse_ms": parse_ms},
            )

    async def copy_normalized_event(
        self,
        db: Any,
        session: CopySession,
        normalized: NormalizedTradeEvent,
        timings: dict[str, float] | None = None,
    ) -> MasterTradeEvent | None:
        timings = timings or {"_received_perf": perf_counter()}
        total_started = timings.get("_received_perf", perf_counter())
        duplicate_started = perf_counter()
        existing = await db.scalar(
            select(MasterTradeEvent).where(
                MasterTradeEvent.session_id == session.id,
                MasterTradeEvent.duplicate_hash == normalized.duplicate_hash,
            )
        )
        timings["duplicate_lookup_ms"] = (perf_counter() - duplicate_started) * 1000
        if existing:
            return None
        scrip_started = perf_counter()
        normalized = await self._resolve_missing_scrip_code(db, session, normalized)
        timings["scrip_code_resolution_ms"] = (perf_counter() - scrip_started) * 1000
        event = MasterTradeEvent(
            session_id=session.id,
            master_account_id=session.master_account_id,
            external_trade_id=normalized.external_trade_id,
            external_order_id=normalized.external_order_id,
            symbol=normalized.symbol,
            exchange=normalized.exchange,
            side=normalized.side,
            quantity=normalized.quantity,
            price=normalized.price,
            order_type=normalized.order_type,
            product_type=normalized.product_type,
            raw_payload_json=normalized.raw_payload,
            event_time=normalized.event_time,
            copied_status="PENDING",
            duplicate_hash=normalized.duplicate_hash,
        )
        db.add(event)
        await db.flush()
        statuses = await self._copy_event_to_targets(db, session, event, normalized, timings)
        event.copied_status = self._event_status(statuses)
        timings["total_master_to_copier_ms"] = (perf_counter() - total_started) * 1000
        event.raw_payload_json = self._payload_with_timings(normalized.raw_payload, timings)
        logger.info(
            "live_copy.master_event_complete",
            extra={
                "session_id": str(session.id),
                "master_account_id": str(session.master_account_id),
                "event_id": str(event.id),
                "symbol": normalized.symbol,
                "exchange": normalized.exchange,
                "status": event.copied_status,
                "target_count": len(statuses),
                "placement_mode": "concurrent",
                "timings_ms": self._public_timings(timings),
            },
        )
        await db.commit()
        await db.refresh(event)
        return event

    @staticmethod
    def _public_timings(timings: dict[str, float]) -> dict[str, float]:
        return {key: round(value, 3) for key, value in timings.items() if not key.startswith("_")}

    def _payload_with_timings(self, payload: dict[str, Any], timings: dict[str, float]) -> dict[str, Any]:
        output = dict(payload)
        output["live_copy_timing_ms"] = self._public_timings(timings)
        return output

    async def _resolve_missing_scrip_code(
        self,
        db: Any,
        session: CopySession,
        normalized: NormalizedTradeEvent,
    ) -> NormalizedTradeEvent:
        if normalized.scrip_code is not None:
            return normalized
        resolution = await script_master_service.resolve(
            db,
            ScriptMasterLookup(
                symbol=normalized.symbol,
                exchange=normalized.exchange,
                segment=normalized.segment,
                instrument_type=normalized.instrument_type,
                option_type=normalized.option_type,
                strike_price=normalized.strike_price,
                expiry_date=normalized.expiry,
                lot_size=normalized.lot_size,
                isin=normalized.isin,
            ),
            account_id=session.master_account_id,
            refresh_stale=False,
        )
        raw_payload = dict(normalized.raw_payload)
        raw_payload["script_master_resolution"] = resolution.to_payload()
        if resolution.resolved:
            logger.info(
                "live_copy.scrip_code_resolved",
                extra={
                    "session_id": str(session.id),
                    "master_account_id": str(session.master_account_id),
                    "symbol": normalized.symbol,
                    "exchange": normalized.exchange,
                    "scrip_code": resolution.scrip_code,
                },
            )
            return replace(
                normalized,
                scrip_code=resolution.scrip_code,
                raw_payload=raw_payload,
                scrip_code_resolution_status=resolution.status,
                scrip_code_resolution_message=resolution.message,
            )
        logger.warning(
            "live_copy.scrip_code_unresolved",
            extra={
                "session_id": str(session.id),
                "master_account_id": str(session.master_account_id),
                "symbol": normalized.symbol,
                "exchange": normalized.exchange,
                "status": resolution.status,
            },
        )
        return replace(
            normalized,
            raw_payload=raw_payload,
            scrip_code_resolution_status=resolution.status,
            scrip_code_resolution_message=resolution.message,
        )

    async def _copy_event_to_targets(
        self,
        db: Any,
        session: CopySession,
        event: MasterTradeEvent,
        normalized: NormalizedTradeEvent,
        timings: dict[str, float],
    ) -> list[CopiedTradeOrderStatus]:
        target_load_started = perf_counter()
        targets = await self._load_copy_targets(db, session, timings)
        timings["target_load_ms"] = (perf_counter() - target_load_started) * 1000
        if not targets:
            return []

        risk_started = perf_counter()
        risk_usage = await self._load_risk_usage(db, targets)
        timings["risk_lookup_ms"] = (perf_counter() - risk_started) * 1000

        dispatch_started = perf_counter()
        results = await self._copy_targets_concurrently(session, normalized, targets, risk_usage)
        timings["order_dispatch_ms"] = (perf_counter() - dispatch_started) * 1000
        timings["copier_target_count"] = len(targets)
        timings["prepared_order_count"] = sum(1 for result in results if result.started_at is not None)
        timings["max_dispatch_gap_ms"] = max((result.dispatch_gap_ms or 0 for result in results), default=0)
        statuses: list[CopiedTradeOrderStatus] = []
        for result in results:
            target = result.target
            copied_order = CopiedTradeOrder(
                master_trade_event_id=event.id,
                copy_group_id=target.copy_group_id,
                copier_account_id=target.copy_account.id,
                request_payload_json=result.request_payload,
                response_payload_json=result.response_payload,
                child_order_id=result.child_order_id,
                status=result.order_status,
                error_message=result.error_message,
            )
            db.add(copied_order)
            statuses.append(result.order_status)
        await db.flush()
        return statuses

    async def _load_copy_targets(
        self,
        db: Any,
        session: CopySession,
        timings: dict[str, float],
    ) -> tuple[CopyTargetPlan, ...]:
        group_ids = tuple(str(value) for value in session.active_group_ids)
        if not group_ids:
            return ()
        cache_key = str(session.id)
        cached = self._target_cache.get(cache_key)
        if (
            cached
            and cached.master_account_id == session.master_account_id
            and cached.group_ids == group_ids
            and perf_counter() - cached.loaded_at <= self._target_cache_ttl_seconds
        ):
            timings["target_cache_hit"] = 1
            logger.info(
                "live_copy.copy_targets_cache_hit",
                extra={"session_id": str(session.id), "target_count": len(cached.targets)},
            )
            return cached.targets

        timings["target_cache_hit"] = 0
        rows = (
            await db.execute(
                select(CopyGroupMember, CopySetting, BrokerAccount, CopyGroup)
                .join(CopyGroup, CopyGroup.id == CopyGroupMember.copy_group_id)
                .join(BrokerAccount, BrokerAccount.id == CopyGroupMember.copy_account_id)
                .outerjoin(
                    CopySetting,
                    (CopySetting.copy_group_id == CopyGroupMember.copy_group_id)
                    & (CopySetting.copy_account_id == CopyGroupMember.copy_account_id),
                )
                .where(
                    CopyGroup.id.in_([uuid.UUID(value) for value in group_ids]),
                    CopyGroup.master_account_id == session.master_account_id,
                    CopyGroupMember.is_enabled.is_(True),
                )
                .order_by(CopyGroup.created_at.asc(), BrokerAccount.account_name.asc())
            )
        ).all()
        targets: list[CopyTargetPlan] = []
        seen_accounts: set[uuid.UUID] = set()
        for member, setting, copy_account, group in rows:
            if copy_account.id in seen_accounts:
                logger.warning(
                    "live_copy.duplicate_copier_skipped",
                    extra={
                        "session_id": str(session.id),
                        "copy_account_id": str(copy_account.id),
                        "copy_group_id": str(group.id),
                    },
                )
                continue
            seen_accounts.add(copy_account.id)
            if not setting:
                setting = self._default_setting(copy_account.id, group.id)
            targets.append(
                CopyTargetPlan(
                    member_id=member.id,
                    copy_group_id=member.copy_group_id,
                    copy_group_name=group.name,
                    setting=setting,
                    copy_account=copy_account,
                )
            )
        cached_targets = tuple(targets)
        self._target_cache[cache_key] = CachedCopyTargets(
            master_account_id=session.master_account_id,
            group_ids=group_ids,
            loaded_at=perf_counter(),
            targets=cached_targets,
        )
        logger.info(
            "live_copy.copy_targets_cache_loaded",
            extra={"session_id": str(session.id), "target_count": len(cached_targets), "group_count": len(group_ids)},
        )
        return cached_targets

    @staticmethod
    def _default_setting(copy_account_id: uuid.UUID, copy_group_id: uuid.UUID) -> CopySetting:
        return CopySetting(
            copy_account_id=copy_account_id,
            copy_group_id=copy_group_id,
            sizing_mode=SizingMode.SAME_QTY,
            multiplier=Decimal("1"),
            allowed_symbols=[],
            blocked_symbols=[],
            allowed_transaction_types=["B", "S"],
            allowed_product_types=[],
            product_type_map={},
            price_mode=PriceMode.SAME_PRICE,
            is_auto_squareoff_enabled=False,
            is_enabled=True,
        )

    async def _load_risk_usage(
        self,
        db: Any,
        targets: tuple[CopyTargetPlan, ...],
    ) -> dict[tuple[uuid.UUID, uuid.UUID], CopyRiskUsage]:
        usage: dict[tuple[uuid.UUID, uuid.UUID], CopyRiskUsage] = {
            (target.copy_group_id, target.copy_account.id): CopyRiskUsage()
            for target in targets
        }
        needs_trade_counts = any(getattr(target.setting, "max_trades_per_day", None) for target in targets)
        needs_daily_loss = any(getattr(target.setting, "max_daily_loss", None) for target in targets)
        trade_counts: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
        if needs_trade_counts:
            day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            rows = (
                await db.execute(
                    select(
                        CopiedTradeOrder.copy_group_id,
                        CopiedTradeOrder.copier_account_id,
                        func.count(CopiedTradeOrder.id),
                    )
                    .where(
                        CopiedTradeOrder.status == CopiedTradeOrderStatus.PLACED,
                        CopiedTradeOrder.created_at >= day_start,
                        CopiedTradeOrder.copy_group_id.in_([target.copy_group_id for target in targets]),
                        CopiedTradeOrder.copier_account_id.in_([target.copy_account.id for target in targets]),
                    )
                    .group_by(CopiedTradeOrder.copy_group_id, CopiedTradeOrder.copier_account_id)
                )
            ).all()
            trade_counts = {
                (copy_group_id, copier_account_id): int(count or 0)
                for copy_group_id, copier_account_id, count in rows
            }

        daily_losses: dict[uuid.UUID, Decimal] = {}
        if needs_daily_loss:
            rows = (
                await db.execute(
                    select(Position.broker_account_id, func.coalesce(func.sum(Position.pnl), 0))
                    .where(Position.broker_account_id.in_([target.copy_account.id for target in targets]))
                    .group_by(Position.broker_account_id)
                )
            ).all()
            for account_id, pnl in rows:
                pnl_value = Decimal(str(pnl or 0))
                daily_losses[account_id] = abs(pnl_value) if pnl_value < 0 else Decimal("0")

        for target in targets:
            key = (target.copy_group_id, target.copy_account.id)
            usage[key] = CopyRiskUsage(
                trades_today=trade_counts.get(key, 0),
                current_daily_loss=daily_losses.get(target.copy_account.id, Decimal("0")),
            )
        return usage

    async def _copy_targets_concurrently(
        self,
        session: CopySession,
        normalized: NormalizedTradeEvent,
        targets: tuple[CopyTargetPlan, ...],
        risk_usage: dict[tuple[uuid.UUID, uuid.UUID], CopyRiskUsage],
    ) -> list[CopyTargetResult]:
        prepared_orders, skipped_results = self._prepare_copy_orders(session, normalized, targets, risk_usage)
        settings = get_settings()
        dispatch_limit = max(0, settings.live_copy_order_dispatch_concurrency)
        if not prepared_orders:
            logger.info(
                "live_copy.dispatch_skipped_no_prepared_orders",
                extra={
                    "session_id": str(session.id),
                    "target_count": len(targets),
                    "skipped_count": len(skipped_results),
                },
            )
            return skipped_results

        dispatch_started_at = _utc_timestamp()
        dispatch_started_perf = perf_counter()
        logger.info(
            "live_copy.dispatch_started",
            extra={
                "session_id": str(session.id),
                "target_count": len(targets),
                "prepared_count": len(prepared_orders),
                "skipped_count": len(skipped_results),
                "placement_mode": "concurrent",
                "dispatch_started_at": dispatch_started_at,
                "dispatch_concurrency_limit": dispatch_limit or "unlimited",
                "broker_throttle_active": dispatch_limit > 0,
            },
        )
        semaphore = asyncio.Semaphore(dispatch_limit) if dispatch_limit > 0 else None
        async with BrokerRouterClient() as broker_router:
            raw_results = await asyncio.gather(
                *[
                    self._place_prepared_order(
                        session,
                        prepared,
                        broker_router,
                        dispatch_started_perf,
                        dispatch_started_at,
                        semaphore,
                    )
                    for prepared in prepared_orders
                ],
                return_exceptions=True,
            )
        dispatched_results = [
            self._result_from_exception(prepared, result)
            if isinstance(result, Exception)
            else result
            for prepared, result in zip(prepared_orders, raw_results, strict=True)
        ]
        dispatched_results = self._with_dispatch_gaps(dispatched_results)
        batch_duration_ms = (perf_counter() - dispatch_started_perf) * 1000
        max_dispatch_gap_ms = max(
            (result.dispatch_gap_ms or 0 for result in dispatched_results),
            default=0,
        )
        logger.info(
            "live_copy.dispatch_completed",
            extra={
                "session_id": str(session.id),
                "prepared_count": len(prepared_orders),
                "skipped_count": len(skipped_results),
                "placed_count": sum(1 for result in dispatched_results if result.order_status == CopiedTradeOrderStatus.PLACED),
                "failed_count": sum(1 for result in dispatched_results if result.order_status == CopiedTradeOrderStatus.FAILED),
                "dispatch_completed_at": _utc_timestamp(),
                "total_batch_duration_ms": round(batch_duration_ms, 3),
                "max_dispatch_gap_ms": round(max_dispatch_gap_ms, 3),
                "placement_mode": "concurrent",
                "broker_throttle_active": dispatch_limit > 0,
            },
        )
        return skipped_results + dispatched_results

    def _prepare_copy_orders(
        self,
        session: CopySession,
        normalized: NormalizedTradeEvent,
        targets: tuple[CopyTargetPlan, ...],
        risk_usage: dict[tuple[uuid.UUID, uuid.UUID], CopyRiskUsage],
    ) -> tuple[tuple[PreparedCopyOrder, ...], list[CopyTargetResult]]:
        settings = get_settings()
        prepared_orders: list[PreparedCopyOrder] = []
        skipped_results: list[CopyTargetResult] = []
        preparation_started = perf_counter()
        for target in targets:
            target_started = perf_counter()
            try:
                request_payload = build_sharekhan_copy_order_payload(
                    normalized,
                    target.setting,
                    target.copy_account,
                    risk_usage.get((target.copy_group_id, target.copy_account.id), CopyRiskUsage()),
                )
            except CopySkip as exc:
                skipped_results.append(
                    CopyTargetResult(
                        target=target,
                        order_status=CopiedTradeOrderStatus.SKIPPED,
                        request_payload={},
                        response_payload={"skipped": True},
                        child_order_id=None,
                        error_message=str(exc),
                        duration_ms=(perf_counter() - target_started) * 1000,
                    )
                )
                logger.info(
                    "live_copy.copier_order_preparation_skipped",
                    extra={
                        "session_id": str(session.id),
                        "copy_group_id": str(target.copy_group_id),
                        "copy_account_id": str(target.copy_account.id),
                        "reason": str(exc),
                    },
                )
                continue

            if session.dry_run or settings.paper_trading_mode or settings.copy_trading_dry_run:
                skipped_results.append(
                    CopyTargetResult(
                        target=target,
                        order_status=CopiedTradeOrderStatus.SKIPPED,
                        request_payload=request_payload,
                        response_payload={"dry_run": True, "message": "Order was not sent to Sharekhan."},
                        child_order_id=None,
                        error_message="DRY_RUN: order not sent to Sharekhan.",
                        duration_ms=(perf_counter() - target_started) * 1000,
                    )
                )
                continue

            prepared_orders.append(PreparedCopyOrder(target=target, request_payload=request_payload))
        logger.info(
            "live_copy.batch_prepared",
            extra={
                "session_id": str(session.id),
                "target_count": len(targets),
                "prepared_count": len(prepared_orders),
                "skipped_count": len(skipped_results),
                "preparation_duration_ms": round((perf_counter() - preparation_started) * 1000, 3),
            },
        )
        return tuple(prepared_orders), skipped_results

    async def _place_prepared_order(
        self,
        session: CopySession,
        prepared: PreparedCopyOrder,
        broker_router: BrokerRouterClient,
        dispatch_started_perf: float,
        dispatch_started_at: str,
        semaphore: asyncio.Semaphore | None,
    ) -> CopyTargetResult:
        if semaphore:
            async with semaphore:
                return await self._place_prepared_order_now(
                    session,
                    prepared,
                    broker_router,
                    dispatch_started_perf,
                    dispatch_started_at,
                )
        return await self._place_prepared_order_now(
            session,
            prepared,
            broker_router,
            dispatch_started_perf,
            dispatch_started_at,
        )

    async def _place_prepared_order_now(
        self,
        session: CopySession,
        prepared: PreparedCopyOrder,
        broker_router: BrokerRouterClient,
        dispatch_started_perf: float,
        dispatch_started_at: str,
    ) -> CopyTargetResult:
        target = prepared.target
        started = perf_counter()
        started_at = _utc_timestamp()
        start_offset_ms = (started - dispatch_started_perf) * 1000
        logger.info(
            "live_copy.copier_order_started",
            extra={
                "session_id": str(session.id),
                "copy_group_id": str(target.copy_group_id),
                "copy_account_id": str(target.copy_account.id),
                "sizing_mode": str(target.setting.sizing_mode),
                "dispatch_started_at": dispatch_started_at,
                "order_started_at": started_at,
                "dispatch_start_offset_ms": round(start_offset_ms, 3),
            },
        )
        try:
            response_payload = await broker_router.place_order(target.copy_account.id, prepared.request_payload)
            order_status = CopiedTradeOrderStatus.PLACED
            child_order_id = extract_child_order_id(response_payload)
            error_message = None
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, default=str)
            order_status = CopiedTradeOrderStatus.FAILED
            response_payload = {"error": exc.detail}
            child_order_id = None
            error_message = detail
        except Exception as exc:
            logger.exception("Live copy order placement failed", extra={"copy_account_id": str(target.copy_account.id)})
            order_status = CopiedTradeOrderStatus.FAILED
            response_payload = {"error": str(exc)}
            child_order_id = None
            error_message = str(exc)
        duration_ms = (perf_counter() - started) * 1000
        completed_at = _utc_timestamp()
        logger.info(
            "live_copy.copier_order_finished",
            extra={
                "session_id": str(session.id),
                "copy_group_id": str(target.copy_group_id),
                "copy_account_id": str(target.copy_account.id),
                "status": order_status.value,
                "duration_ms": round(duration_ms, 3),
                "order_started_at": started_at,
                "order_completed_at": completed_at,
                "dispatch_start_offset_ms": round(start_offset_ms, 3),
            },
        )
        return CopyTargetResult(
            target=target,
            order_status=order_status,
            request_payload=prepared.request_payload,
            response_payload=response_payload,
            child_order_id=child_order_id,
            error_message=error_message,
            duration_ms=duration_ms,
            dispatch_started_at=dispatch_started_at,
            started_at=started_at,
            completed_at=completed_at,
            start_offset_ms=start_offset_ms,
        )

    @staticmethod
    def _result_from_exception(prepared: PreparedCopyOrder, exc: Exception) -> CopyTargetResult:
        logger.error(
            "Live copy dispatch task crashed",
            extra={"copy_account_id": str(prepared.target.copy_account.id)},
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        timestamp = _utc_timestamp()
        return CopyTargetResult(
            target=prepared.target,
            order_status=CopiedTradeOrderStatus.FAILED,
            request_payload=prepared.request_payload,
            response_payload={"error": str(exc)},
            child_order_id=None,
            error_message=str(exc),
            duration_ms=0,
            started_at=timestamp,
            completed_at=timestamp,
        )

    @staticmethod
    def _with_dispatch_gaps(results: list[CopyTargetResult]) -> list[CopyTargetResult]:
        indexed_offsets = sorted(
            (index, result.start_offset_ms)
            for index, result in enumerate(results)
            if result.start_offset_ms is not None
        )
        previous_offset: float | None = None
        output = list(results)
        for index, offset in indexed_offsets:
            gap = 0.0 if previous_offset is None else offset - previous_offset
            output[index] = replace(output[index], dispatch_gap_ms=gap)
            previous_offset = offset
        return output

    async def _copy_one_target(
        self,
        session: CopySession,
        normalized: NormalizedTradeEvent,
        setting: CopySetting,
        copy_account: BrokerAccount,
        risk_usage: CopyRiskUsage | None = None,
    ) -> tuple[CopiedTradeOrderStatus, dict[str, Any], dict[str, Any], str | None, str | None]:
        try:
            request_payload = build_sharekhan_copy_order_payload(normalized, setting, copy_account, risk_usage)
        except CopySkip as exc:
            return CopiedTradeOrderStatus.SKIPPED, {}, {"skipped": True}, None, str(exc)

        settings = get_settings()
        if session.dry_run or settings.paper_trading_mode or settings.copy_trading_dry_run:
            return (
                CopiedTradeOrderStatus.SKIPPED,
                request_payload,
                {"dry_run": True, "message": "Order was not sent to Sharekhan."},
                None,
                "DRY_RUN: order not sent to Sharekhan.",
            )
        try:
            response = await BrokerRouterClient().place_order(copy_account.id, request_payload)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, default=str)
            return CopiedTradeOrderStatus.FAILED, request_payload, {"error": exc.detail}, None, detail
        except Exception as exc:
            logger.exception("Live copy order placement failed", extra={"copy_account_id": str(copy_account.id)})
            return CopiedTradeOrderStatus.FAILED, request_payload, {"error": str(exc)}, None, str(exc)
        return CopiedTradeOrderStatus.PLACED, request_payload, response, extract_child_order_id(response), None

    @staticmethod
    def _event_status(statuses: list[CopiedTradeOrderStatus]) -> str:
        if not statuses:
            return "SKIPPED"
        if all(status == CopiedTradeOrderStatus.PLACED for status in statuses):
            return "PLACED"
        if any(status == CopiedTradeOrderStatus.PLACED for status in statuses):
            return "PARTIAL"
        if any(status == CopiedTradeOrderStatus.FAILED for status in statuses):
            return "FAILED"
        return "SKIPPED"


live_copy_manager = LiveCopyManager()
