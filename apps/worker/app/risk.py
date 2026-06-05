import hashlib
import math
import uuid
from dataclasses import dataclass, field
from datetime import datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo


class RiskRejected(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class MasterOrder:
    id: uuid.UUID
    broker_order_id: str
    exchange: str
    scrip_code: str
    trading_symbol: str
    transaction_type: str
    quantity: int
    price: Decimal
    trigger_price: Decimal = Decimal("0")
    order_type: str = "NORMAL"
    product_type: str = "INVESTMENT"
    request_type: str = "NEW"
    raw_payload: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CopyAccount:
    id: uuid.UUID
    customer_id: str
    login_id: str
    is_active: bool
    has_token: bool
    capital: Decimal | None = None


@dataclass(frozen=True)
class CopySettings:
    is_enabled: bool = True
    sizing_mode: str = "SAME_QTY"
    multiplier: Decimal = Decimal("1")
    fixed_qty: int | None = None
    capital_percent: Decimal | None = None
    max_qty: int | None = None
    max_order_value: Decimal | None = None
    allowed_symbols: list[str] = field(default_factory=list)
    blocked_symbols: list[str] = field(default_factory=list)
    allowed_transaction_types: list[str] = field(default_factory=lambda: ["B", "S"])
    allowed_product_types: list[str] = field(default_factory=list)
    product_type_map: dict[str, str] = field(default_factory=dict)
    price_mode: str = "SAME_PRICE"
    max_slippage_percent: Decimal | None = None
    is_auto_squareoff_enabled: bool = False


@dataclass(frozen=True)
class CopyTarget:
    account: CopyAccount
    settings: CopySettings


def idempotency_key(master_order_id: uuid.UUID, copy_account_id: uuid.UUID, request_type: str) -> str:
    raw = f"{master_order_id}:{copy_account_id}:{request_type.upper()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calculate_quantity(master_order: MasterOrder, settings: CopySettings, copy_account: CopyAccount) -> int:
    if settings.sizing_mode == "SAME_QTY":
        return master_order.quantity
    if settings.sizing_mode == "MULTIPLIER":
        return math.floor(master_order.quantity * settings.multiplier)
    if settings.sizing_mode == "FIXED_QTY":
        if not settings.fixed_qty:
            raise RiskRejected("fixed quantity is required")
        return settings.fixed_qty
    if settings.sizing_mode == "PERCENT_CAPITAL":
        if copy_account.capital is None:
            raise RiskRejected("copy account capital is required")
        if settings.capital_percent is None:
            raise RiskRejected("capital percent is required")
        if master_order.price <= 0:
            raise RiskRejected("order price must be greater than zero")
        allocation = copy_account.capital * settings.capital_percent / Decimal("100")
        return math.floor(allocation / master_order.price)
    raise RiskRejected(f"unsupported sizing mode {settings.sizing_mode}")


def is_market_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(ZoneInfo("Asia/Kolkata"))
    if current.tzinfo is None:
        current = current.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    local = current.astimezone(ZoneInfo("Asia/Kolkata"))
    if local.weekday() >= 5:
        return False
    return time(9, 15) <= local.time() <= time(15, 30)


def validate_risk(
    master_order: MasterOrder,
    target: CopyTarget,
    *,
    now: datetime | None = None,
    enforce_market_hours: bool = True,
) -> int:
    account = target.account
    settings = target.settings
    symbol = master_order.trading_symbol.upper()
    product_type = master_order.product_type.upper()
    transaction_type = master_order.transaction_type.upper()

    if not account.is_active:
        raise RiskRejected("account is inactive")
    if not account.has_token:
        raise RiskRejected("access token is missing")
    if not settings.is_enabled:
        raise RiskRejected("copy setting is disabled")
    if enforce_market_hours and not is_market_open(now):
        raise RiskRejected("market is closed")

    blocked = {item.upper() for item in settings.blocked_symbols}
    allowed = {item.upper() for item in settings.allowed_symbols}
    if symbol in blocked:
        raise RiskRejected("symbol is blocked")
    if allowed and symbol not in allowed:
        raise RiskRejected("symbol is not allowed")

    allowed_transactions = {item.upper() for item in settings.allowed_transaction_types}
    if allowed_transactions and transaction_type not in allowed_transactions:
        raise RiskRejected("transaction type is not allowed")

    allowed_products = {item.upper() for item in settings.allowed_product_types}
    if allowed_products and product_type not in allowed_products:
        raise RiskRejected("product type is not allowed")

    quantity = calculate_quantity(master_order, settings, account)
    if quantity <= 0:
        raise RiskRejected("calculated quantity must be greater than zero")
    if settings.max_qty is not None and quantity > settings.max_qty:
        raise RiskRejected("quantity exceeds max quantity")
    order_value = Decimal(quantity) * master_order.price
    if settings.max_order_value is not None and order_value > settings.max_order_value:
        raise RiskRejected("order value exceeds max order value")
    return quantity


def mapped_product_type(master_order: MasterOrder, settings: CopySettings) -> str:
    return settings.product_type_map.get(master_order.product_type, master_order.product_type)


def calculated_price(master_order: MasterOrder, settings: CopySettings) -> Decimal:
    if settings.price_mode == "MARKET":
        return Decimal("0")
    if settings.price_mode == "LIMIT_WITH_SLIPPAGE":
        slippage = settings.max_slippage_percent or Decimal("0")
        factor = Decimal("1") + (slippage / Decimal("100"))
        if master_order.transaction_type.upper() == "S":
            factor = Decimal("1") - (slippage / Decimal("100"))
        return (master_order.price * factor).quantize(Decimal("0.01"))
    return master_order.price


def copy_order_payload(master_order: MasterOrder, target: CopyTarget, quantity: int) -> dict:
    price = calculated_price(master_order, target.settings)
    return {
        "customerId": target.account.customer_id,
        "scripCode": int(master_order.scrip_code),
        "tradingSymbol": master_order.trading_symbol,
        "exchange": master_order.exchange,
        "transactionType": master_order.transaction_type,
        "quantity": quantity,
        "disclosedQty": 0,
        "price": str(price),
        "triggerPrice": str(master_order.trigger_price),
        "rmsCode": master_order.raw_payload.get("rmsCode", "ANY"),
        "afterHour": master_order.raw_payload.get("afterHour", "N"),
        "orderType": master_order.order_type,
        "channelUser": target.account.login_id,
        "validity": master_order.raw_payload.get("validity", "GFD"),
        "requestType": master_order.request_type,
        "productType": mapped_product_type(master_order, target.settings),
    }
