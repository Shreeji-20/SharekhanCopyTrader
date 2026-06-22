import enum
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import BIGINT, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class UserRole(str, enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class Broker(str, enum.Enum):
    SHAREKHAN = "SHAREKHAN"


class AccountType(str, enum.Enum):
    MASTER = "MASTER"
    COPY = "COPY"


class SizingMode(str, enum.Enum):
    SAME_QTY = "SAME_QTY"
    MULTIPLIER = "MULTIPLIER"
    FIXED_QTY = "FIXED_QTY"
    PERCENT_CAPITAL = "PERCENT_CAPITAL"


class PriceMode(str, enum.Enum):
    SAME_PRICE = "SAME_PRICE"
    MARKET = "MARKET"
    LIMIT_WITH_SLIPPAGE = "LIMIT_WITH_SLIPPAGE"


class CopyOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"


class CopySessionStatus(str, enum.Enum):
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    ERROR = "ERROR"


class CopiedTradeOrderStatus(str, enum.Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role"), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    accounts: Mapped[list["BrokerAccount"]] = relationship(back_populates="user")


class BrokerAccount(Base):
    __tablename__ = "broker_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    broker: Mapped[Broker] = mapped_column(Enum(Broker, name="broker"), default=Broker.SHAREKHAN, nullable=False)
    account_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    login_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)
    secret_key: Mapped[str] = mapped_column(Text, nullable=False)
    vendor_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_scheme: Mapped[str | None] = mapped_column(String(10), nullable=True)
    proxy_host: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    proxy_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    proxy_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    sharekhan_login_state: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    request_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_type: Mapped[AccountType] = mapped_column(Enum(AccountType, name="account_type"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="accounts")
    copy_settings: Mapped[list["CopySetting"]] = relationship(back_populates="copy_account")


class CopyGroup(Base):
    __tablename__ = "copy_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    master_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    master_account: Mapped[BrokerAccount] = relationship(foreign_keys=[master_account_id])
    members: Mapped[list["CopyGroupMember"]] = relationship(back_populates="copy_group", cascade="all, delete-orphan")


class CopyGroupMember(Base):
    __tablename__ = "copy_group_members"
    __table_args__ = (UniqueConstraint("copy_group_id", "copy_account_id", name="uq_copy_group_member"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    copy_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copy_groups.id", ondelete="CASCADE"))
    copy_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    copy_group: Mapped[CopyGroup] = relationship(back_populates="members")
    copy_account: Mapped[BrokerAccount] = relationship(foreign_keys=[copy_account_id])


class CopySetting(Base):
    __tablename__ = "copy_settings"
    __table_args__ = (UniqueConstraint("copy_account_id", "copy_group_id", name="uq_copy_settings_account_group"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    copy_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    copy_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copy_groups.id", ondelete="CASCADE"))
    sizing_mode: Mapped[SizingMode] = mapped_column(Enum(SizingMode, name="sizing_mode"), default=SizingMode.SAME_QTY)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1"), nullable=False)
    fixed_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capital_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    min_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_trades_per_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_daily_loss: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    max_order_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    allowed_symbols: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    blocked_symbols: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    allowed_transaction_types: Mapped[list[str]] = mapped_column(JSONB, default=lambda: ["B", "S"], nullable=False)
    allowed_product_types: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    product_type_map: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    price_mode: Mapped[PriceMode] = mapped_column(Enum(PriceMode, name="price_mode"), default=PriceMode.SAME_PRICE)
    max_slippage_percent: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    is_auto_squareoff_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    copy_account: Mapped[BrokerAccount] = relationship(back_populates="copy_settings", foreign_keys=[copy_account_id])
    copy_group: Mapped[CopyGroup] = relationship(foreign_keys=[copy_group_id])


class MasterOrder(Base):
    __tablename__ = "master_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_order_id: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    master_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    scrip_code: Mapped[str] = mapped_column(String(40), nullable=False)
    trading_symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    trigger_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    order_type: Mapped[str] = mapped_column(String(40), nullable=False)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False)
    request_type: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    raw_response: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    master_account: Mapped[BrokerAccount] = relationship(foreign_keys=[master_account_id])


class CopyOrder(Base):
    __tablename__ = "copy_orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    master_order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("master_orders.id", ondelete="CASCADE"))
    copy_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    broker_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[CopyOrderStatus] = mapped_column(
        Enum(CopyOrderStatus, name="copy_order_status"), default=CopyOrderStatus.PENDING, nullable=False
    )
    calculated_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    calculated_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    master_order: Mapped[MasterOrder] = relationship(foreign_keys=[master_order_id])
    copy_account: Mapped[BrokerAccount] = relationship(foreign_keys=[copy_account_id])


class CopySession(Base):
    __tablename__ = "copy_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    master_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    status: Mapped[CopySessionStatus] = mapped_column(
        Enum(CopySessionStatus, name="copy_session_status"), default=CopySessionStatus.RUNNING, nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    active_group_ids: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    master_account: Mapped[BrokerAccount] = relationship(foreign_keys=[master_account_id])


class MasterTradeEvent(Base):
    __tablename__ = "master_trade_events"
    __table_args__ = (
        UniqueConstraint("session_id", "external_trade_id", name="uq_master_trade_event_session_trade"),
        UniqueConstraint("session_id", "duplicate_hash", name="uq_master_trade_event_session_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copy_sessions.id", ondelete="CASCADE"))
    master_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    external_trade_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    external_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(40), nullable=False)
    product_type: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    copied_status: Mapped[str] = mapped_column(String(40), default="PENDING", nullable=False)
    duplicate_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    session: Mapped[CopySession] = relationship(foreign_keys=[session_id])


class CopiedTradeOrder(Base):
    __tablename__ = "copied_trade_orders"
    __table_args__ = (UniqueConstraint("master_trade_event_id", "copier_account_id", name="uq_copied_trade_order_event_account"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    master_trade_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("master_trade_events.id", ondelete="CASCADE")
    )
    copy_group_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("copy_groups.id", ondelete="CASCADE"))
    copier_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    request_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    response_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    child_order_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[CopiedTradeOrderStatus] = mapped_column(
        Enum(CopiedTradeOrderStatus, name="copied_trade_order_status"),
        default=CopiedTradeOrderStatus.PENDING,
        nullable=False,
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    master_trade_event: Mapped[MasterTradeEvent] = relationship(foreign_keys=[master_trade_event_id])
    copy_group: Mapped[CopyGroup] = relationship(foreign_keys=[copy_group_id])
    copier_account: Mapped[BrokerAccount] = relationship(foreign_keys=[copier_account_id])


class ScriptMasterInstrument(Base):
    __tablename__ = "script_master_instruments"
    __table_args__ = (
        UniqueConstraint("exchange", "scrip_code", name="uq_script_master_exchange_scrip_code"),
        Index("ix_script_master_exchange_symbol", "exchange", "trading_symbol"),
        Index("ix_script_master_exchange_segment_symbol", "exchange", "segment", "trading_symbol"),
        Index(
            "ix_script_master_derivative_lookup",
            "exchange",
            "instrument_type",
            "trading_symbol",
            "expiry_date",
            "strike_price",
            "option_type",
        ),
        Index("ix_script_master_underlying_symbol", "underlying_symbol"),
        Index("ix_script_master_isin", "isin"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    segment: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scrip_code: Mapped[str] = mapped_column(String(40), nullable=False)
    trading_symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    symbol_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    underlying_symbol: Mapped[str | None] = mapped_column(String(120), nullable=True)
    instrument_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    option_type: Mapped[str | None] = mapped_column(String(10), nullable=True)
    strike_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lot_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    raw_payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ScriptMasterWatchlistItem(Base):
    __tablename__ = "script_master_watchlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "account_id", "exchange", "scrip_code", name="uq_script_master_watchlist_user_account_scrip"),
        Index("ix_script_master_watchlist_user_account", "user_id", "account_id"),
        Index("ix_script_master_watchlist_exchange_scrip", "exchange", "scrip_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    scrip_code: Mapped[str] = mapped_column(String(40), nullable=False)
    instrument_snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    account: Mapped[BrokerAccount] = relationship(foreign_keys=[account_id])


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    scrip_code: Mapped[str] = mapped_column(String(40), nullable=False)
    trading_symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    avg_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    pnl: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Holding(Base):
    __tablename__ = "holdings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    broker_trade_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    scrip_code: Mapped[str] = mapped_column(String(40), nullable=False)
    trading_symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    traded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WebsocketTick(Base):
    __tablename__ = "websocket_ticks"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    broker_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("broker_accounts.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(120), nullable=False)
    exchange: Mapped[str] = mapped_column(String(20), nullable=False)
    tick_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
