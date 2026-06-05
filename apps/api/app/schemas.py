import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import (
    AccountType,
    Broker,
    CopiedTradeOrderStatus,
    CopyOrderStatus,
    CopySessionStatus,
    PriceMode,
    SizingMode,
    UserRole,
)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10)


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _normalize_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


class ProxyFieldsMixin(BaseModel):
    proxy_scheme: Literal["http", "https"] | None = None
    proxy_host: str | None = Field(default=None, max_length=255)
    proxy_port: int | None = Field(default=None, ge=1, le=65535)
    proxy_username: str | None = Field(default=None, max_length=255)
    proxy_password: str | None = Field(default=None, max_length=255)

    @field_validator("proxy_host", "proxy_username", "proxy_password")
    @classmethod
    def normalize_proxy_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_string(value)

    @model_validator(mode="after")
    def validate_proxy_fields(self) -> "ProxyFieldsMixin":
        has_proxy_value = any(
            value not in (None, "")
            for value in (self.proxy_host, self.proxy_port, self.proxy_username, self.proxy_password)
        )
        if not has_proxy_value:
            self.proxy_scheme = None
            return self
        self.proxy_scheme = self.proxy_scheme or "http"
        if not self.proxy_host:
            raise ValueError("proxy_host is required when proxy details are provided")
        if self.proxy_port is None:
            raise ValueError("proxy_port is required when proxy details are provided")
        if self.proxy_password and not self.proxy_username:
            raise ValueError("proxy_username is required when proxy_password is provided")
        return self


class BrokerAccountCreate(ProxyFieldsMixin):
    account_name: str = Field(min_length=1, max_length=120)
    customer_id: str | None = Field(default=None, max_length=80)
    login_id: str | None = Field(default=None, max_length=120)
    api_key: str = Field(min_length=1)
    secret_key: str = Field(min_length=1)
    vendor_key: str | None = None
    account_type: AccountType

    @field_validator("customer_id", "login_id", "vendor_key")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_string(value)


class BrokerAccountUpdate(ProxyFieldsMixin):
    account_name: str | None = Field(default=None, min_length=1, max_length=120)
    customer_id: str | None = Field(default=None, max_length=80)
    login_id: str | None = Field(default=None, max_length=120)
    api_key: str | None = Field(default=None, min_length=1)
    secret_key: str | None = Field(default=None, min_length=1)
    vendor_key: str | None = None
    account_type: AccountType | None = None
    is_active: bool | None = None

    @field_validator("customer_id", "login_id", "vendor_key")
    @classmethod
    def normalize_optional_strings(cls, value: str | None) -> str | None:
        return _normalize_optional_string(value)


class BrokerAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker: Broker
    account_name: str
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
    request_token: str | None
    access_token: str | None
    refresh_token: str | None
    token_expires_at: datetime | None
    credentials_readable: bool
    account_type: AccountType
    is_active: bool
    last_connected_at: datetime | None
    created_at: datetime
    updated_at: datetime


class SharekhanTokenExchange(BaseModel):
    request_token: str = Field(min_length=1)


class SharekhanCallbackExchange(BaseModel):
    state: str | None = Field(default=None, min_length=1)
    account_id: uuid.UUID | None = None
    request_token: str = Field(min_length=1)


class SharekhanWsSubscription(BaseModel):
    symbols: list[str] = Field(min_length=1)
    exchange: str = Field(min_length=1, max_length=20)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value if item.strip()]
        if not normalized:
            raise ValueError("symbols must contain at least one non-blank value")
        return normalized

    @field_validator("exchange")
    @classmethod
    def normalize_exchange(cls, value: str) -> str:
        return value.strip().upper()


class CopyGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    master_account_id: uuid.UUID
    is_active: bool = True

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_string(value)


class CopyGroupUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=1000)
    master_account_id: uuid.UUID | None = None
    is_active: bool | None = None

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return _normalize_optional_string(value)


class CopyGroupRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    master_account_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CopyGroupAccountRead(BaseModel):
    id: uuid.UUID
    account_name: str
    account_type: AccountType
    customer_id: str | None
    login_id: str | None
    is_active: bool


class CopyGroupMemberSettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    copy_account_id: uuid.UUID
    copy_group_id: uuid.UUID
    sizing_mode: SizingMode
    multiplier: Decimal
    fixed_qty: int | None
    capital_percent: Decimal | None
    max_qty: int | None
    max_order_value: Decimal | None
    allowed_symbols: list[str]
    blocked_symbols: list[str]
    allowed_transaction_types: list[str]
    allowed_product_types: list[str]
    product_type_map: dict[str, str]
    price_mode: PriceMode
    max_slippage_percent: Decimal | None
    is_auto_squareoff_enabled: bool
    is_enabled: bool


class CopyGroupMemberDetailRead(BaseModel):
    id: uuid.UUID
    copy_group_id: uuid.UUID
    copy_account_id: uuid.UUID
    copy_account: CopyGroupAccountRead
    copy_setting: CopyGroupMemberSettingRead | None = None
    is_enabled: bool
    created_at: datetime


class DuplicateCopyAccountWarning(BaseModel):
    copy_account_id: uuid.UUID
    account_name: str
    copy_group_ids: list[uuid.UUID]


class CopyGroupDetailRead(CopyGroupRead):
    master_account_name: str | None = None
    members: list[CopyGroupMemberDetailRead] = Field(default_factory=list)


class CopyGroupValidationRequest(BaseModel):
    master_account_id: uuid.UUID
    copy_group_ids: list[uuid.UUID] = Field(min_length=1)


class CopyGroupValidationRead(BaseModel):
    ok: bool
    warnings: list[str] = Field(default_factory=list)
    duplicate_copy_accounts: list[DuplicateCopyAccountWarning] = Field(default_factory=list)
    copy_account_count: int = 0


class CopyGroupMemberCreate(BaseModel):
    copy_account_id: uuid.UUID
    is_enabled: bool = True


class CopyGroupMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    copy_group_id: uuid.UUID
    copy_account_id: uuid.UUID
    is_enabled: bool
    created_at: datetime


class CopySettingPatch(BaseModel):
    copy_group_id: uuid.UUID | None = None
    sizing_mode: SizingMode | None = None
    multiplier: Decimal | None = None
    fixed_qty: int | None = Field(default=None, ge=1)
    capital_percent: Decimal | None = Field(default=None, gt=0, le=100)
    max_qty: int | None = Field(default=None, ge=1)
    max_order_value: Decimal | None = Field(default=None, gt=0)
    allowed_symbols: list[str] | None = None
    blocked_symbols: list[str] | None = None
    allowed_transaction_types: list[str] | None = None
    allowed_product_types: list[str] | None = None
    product_type_map: dict[str, str] | None = None
    price_mode: PriceMode | None = None
    max_slippage_percent: Decimal | None = Field(default=None, ge=0)
    is_auto_squareoff_enabled: bool | None = None
    is_enabled: bool | None = None


class CopySettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    copy_account_id: uuid.UUID
    copy_group_id: uuid.UUID
    sizing_mode: SizingMode
    multiplier: Decimal
    fixed_qty: int | None
    capital_percent: Decimal | None
    max_qty: int | None
    max_order_value: Decimal | None
    allowed_symbols: list[str]
    blocked_symbols: list[str]
    allowed_transaction_types: list[str]
    allowed_product_types: list[str]
    product_type_map: dict[str, str]
    price_mode: PriceMode
    max_slippage_percent: Decimal | None
    is_auto_squareoff_enabled: bool
    is_enabled: bool


class MasterOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker_order_id: str
    master_account_id: uuid.UUID
    exchange: str
    scrip_code: str
    trading_symbol: str
    transaction_type: str
    quantity: int
    price: Decimal
    trigger_price: Decimal | None
    order_type: str
    product_type: str
    request_type: str
    status: str
    created_at: datetime


class CopyOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    master_order_id: uuid.UUID
    copy_account_id: uuid.UUID
    broker_order_id: str | None
    status: CopyOrderStatus
    calculated_quantity: int
    calculated_price: Decimal
    error_message: str | None
    retry_count: int
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class CopySessionStart(BaseModel):
    master_account_id: uuid.UUID
    copy_group_ids: list[uuid.UUID] = Field(min_length=1)
    dry_run: bool | None = None
    allow_duplicate_copiers: bool = False


class CopySessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    master_account_id: uuid.UUID
    status: CopySessionStatus
    started_at: datetime
    paused_at: datetime | None
    resumed_at: datetime | None
    stopped_at: datetime | None
    last_error: str | None
    active_group_ids: list[uuid.UUID]
    dry_run: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MasterTradeEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    master_account_id: uuid.UUID
    external_trade_id: str | None
    external_order_id: str | None
    symbol: str
    exchange: str
    side: str
    quantity: int
    price: Decimal
    order_type: str
    product_type: str
    raw_payload_json: dict[str, Any]
    event_time: datetime | None
    copied_status: str
    duplicate_hash: str
    created_at: datetime


class CopiedTradeOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    master_trade_event_id: uuid.UUID
    copy_group_id: uuid.UUID
    copier_account_id: uuid.UUID
    request_payload_json: dict[str, Any]
    response_payload_json: dict[str, Any]
    child_order_id: str | None
    status: CopiedTradeOrderStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker_account_id: uuid.UUID
    exchange: str
    scrip_code: str
    trading_symbol: str
    quantity: int
    avg_price: Decimal
    pnl: Decimal
    synced_at: datetime


class HoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker_account_id: uuid.UUID
    raw_payload: dict[str, Any]
    synced_at: datetime


class TradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    broker_account_id: uuid.UUID
    broker_trade_id: str | None
    exchange: str
    scrip_code: str
    trading_symbol: str
    transaction_type: str
    quantity: int
    price: Decimal
    traded_at: datetime | None
    synced_at: datetime


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    metadata_: dict[str, Any] = Field(alias="metadata")
    created_at: datetime


class SharekhanOrderPayload(BaseModel):
    customerId: str | None = None
    scripCode: int | None = None
    tradingSymbol: str | None = None
    exchange: str | None = None
    transactionType: Literal["B", "S"] | None = None
    quantity: int | None = Field(default=None, gt=0)
    disclosedQty: int = Field(ge=0, default=0)
    price: Decimal | None = Field(default=None, ge=0)
    triggerPrice: Decimal = Field(ge=0, default=Decimal("0"))
    rmsCode: str = "ANY"
    afterHour: Literal["Y", "N"] = "N"
    orderType: str = "NORMAL"
    channelUser: str | None = None
    validity: str = "GFD"
    requestType: Literal["NEW", "MODIFY", "CANCEL"] = "NEW"
    productType: str | None = "INVESTMENT"
    orderId: str | None = None
    instrumentType: str | None = None
    strikePrice: Decimal | None = None
    optionType: str | None = None
    expiry: str | None = None

    @field_validator("tradingSymbol", "exchange", "productType")
    @classmethod
    def uppercase_required_fields(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        if not value:
            raise ValueError("field cannot be blank")
        return value.upper()

    @model_validator(mode="after")
    def validate_order_action(self) -> "SharekhanOrderPayload":
        required_for_new = [
            "customerId",
            "scripCode",
            "tradingSymbol",
            "exchange",
            "transactionType",
            "quantity",
            "price",
            "channelUser",
            "productType",
        ]
        if self.requestType == "NEW":
            missing = [field for field in required_for_new if getattr(self, field) in (None, "")]
            if missing:
                raise ValueError(f"missing required fields for NEW order: {', '.join(missing)}")
        if self.requestType in {"MODIFY", "CANCEL"} and not self.orderId:
            raise ValueError("orderId is required for MODIFY and CANCEL")
        return self


class DashboardMetrics(BaseModel):
    master_orders_today: int
    successful_copied_orders: int
    failed_copy_orders: int
    active_copy_accounts: int
    open_positions: int
    total_pnl: Decimal
    broker_connection_status: Literal["CONNECTED", "DEGRADED", "DISCONNECTED"]
