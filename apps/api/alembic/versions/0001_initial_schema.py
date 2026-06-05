"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = postgresql.ENUM("ADMIN", "USER", name="user_role")
    broker = postgresql.ENUM("SHAREKHAN", name="broker")
    account_type = postgresql.ENUM("MASTER", "COPY", name="account_type")
    sizing_mode = postgresql.ENUM("SAME_QTY", "MULTIPLIER", "FIXED_QTY", "PERCENT_CAPITAL", name="sizing_mode")
    price_mode = postgresql.ENUM("SAME_PRICE", "MARKET", "LIMIT_WITH_SLIPPAGE", name="price_mode")
    copy_order_status = postgresql.ENUM(
        "PENDING", "SENT", "SUCCESS", "FAILED", "SKIPPED", "RETRYING", name="copy_order_status"
    )
    for enum_type in (user_role, broker, account_type, sizing_mode, price_mode, copy_order_status):
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", postgresql.ENUM("ADMIN", "USER", name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.create_table(
        "broker_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("broker", postgresql.ENUM("SHAREKHAN", name="broker", create_type=False), nullable=False),
        sa.Column("account_name", sa.String(length=120), nullable=False),
        sa.Column("customer_id", sa.String(length=80), nullable=False),
        sa.Column("login_id", sa.String(length=120), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=False),
        sa.Column("secret_key", sa.Text(), nullable=False),
        sa.Column("vendor_key", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_type", postgresql.ENUM("MASTER", "COPY", name="account_type", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "copy_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "master_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "copy_group_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "copy_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copy_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "copy_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("copy_group_id", "copy_account_id", name="uq_copy_group_member"),
    )

    op.create_table(
        "copy_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "copy_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "copy_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("copy_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "sizing_mode",
            postgresql.ENUM("SAME_QTY", "MULTIPLIER", "FIXED_QTY", "PERCENT_CAPITAL", name="sizing_mode", create_type=False),
            nullable=False,
        ),
        sa.Column("multiplier", sa.Numeric(18, 6), nullable=False),
        sa.Column("fixed_qty", sa.Integer(), nullable=True),
        sa.Column("capital_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("max_qty", sa.Integer(), nullable=True),
        sa.Column("max_order_value", sa.Numeric(18, 2), nullable=True),
        sa.Column("allowed_symbols", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("blocked_symbols", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_transaction_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("allowed_product_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("product_type_map", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "price_mode",
            postgresql.ENUM("SAME_PRICE", "MARKET", "LIMIT_WITH_SLIPPAGE", name="price_mode", create_type=False),
            nullable=False,
        ),
        sa.Column("max_slippage_percent", sa.Numeric(8, 4), nullable=True),
        sa.Column("is_auto_squareoff_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("copy_account_id", "copy_group_id", name="uq_copy_settings_account_group"),
    )

    op.create_table(
        "master_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("broker_order_id", sa.String(length=120), nullable=False),
        sa.Column(
            "master_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("scrip_code", sa.String(length=40), nullable=False),
        sa.Column("trading_symbol", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("trigger_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("order_type", sa.String(length=40), nullable=False),
        sa.Column("product_type", sa.String(length=80), nullable=False),
        sa.Column("request_type", sa.String(length=20), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(op.f("ix_master_orders_broker_order_id"), "master_orders", ["broker_order_id"], unique=False)

    op.create_table(
        "copy_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "master_order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("master_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "copy_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker_order_id", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING", "SENT", "SUCCESS", "FAILED", "SKIPPED", "RETRYING", name="copy_order_status", create_type=False
            ),
            nullable=False,
        ),
        sa.Column("calculated_quantity", sa.Integer(), nullable=False),
        sa.Column("calculated_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )

    op.create_table(
        "positions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "broker_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("scrip_code", sa.String(length=40), nullable=False),
        sa.Column("trading_symbol", sa.String(length=120), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("avg_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("pnl", sa.Numeric(18, 4), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "broker_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "trades",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "broker_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("broker_trade_id", sa.String(length=120), nullable=True),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("scrip_code", sa.String(length=40), nullable=False),
        sa.Column("trading_symbol", sa.String(length=120), nullable=False),
        sa.Column("transaction_type", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("traded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("entity_type", sa.String(length=120), nullable=False),
        sa.Column("entity_id", sa.String(length=120), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "websocket_ticks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column(
            "broker_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("tick_data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    for table_name in (
        "websocket_ticks",
        "audit_logs",
        "trades",
        "holdings",
        "positions",
        "copy_orders",
        "master_orders",
        "copy_settings",
        "copy_group_members",
        "copy_groups",
        "broker_accounts",
        "users",
    ):
        op.drop_table(table_name)

    for enum_name in (
        "copy_order_status",
        "price_mode",
        "sizing_mode",
        "account_type",
        "broker",
        "user_role",
    ):
        postgresql.ENUM(name=enum_name).drop(op.get_bind(), checkfirst=True)
