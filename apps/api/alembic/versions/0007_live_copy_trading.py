"""add live copy trading tables

Revision ID: 0007_live_copy_trading
Revises: 0006_sharekhan_login_state
Create Date: 2026-06-04 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0007_live_copy_trading"
down_revision: str | None = "0006_sharekhan_login_state"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    copy_session_status = postgresql.ENUM("RUNNING", "PAUSED", "STOPPED", "ERROR", name="copy_session_status")
    copied_trade_order_status = postgresql.ENUM("PENDING", "PLACED", "FAILED", "SKIPPED", name="copied_trade_order_status")
    copy_session_status.create(op.get_bind(), checkfirst=True)
    copied_trade_order_status.create(op.get_bind(), checkfirst=True)

    op.add_column("copy_groups", sa.Column("description", sa.Text(), nullable=True))

    op.create_table(
        "copy_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "master_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", postgresql.ENUM("RUNNING", "PAUSED", "STOPPED", "ERROR", name="copy_session_status", create_type=False), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("active_group_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "master_trade_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("copy_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "master_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_trade_id", sa.String(length=120), nullable=True),
        sa.Column("external_order_id", sa.String(length=120), nullable=True),
        sa.Column("symbol", sa.String(length=120), nullable=False),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 4), nullable=False),
        sa.Column("order_type", sa.String(length=40), nullable=False),
        sa.Column("product_type", sa.String(length=80), nullable=False),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("copied_status", sa.String(length=40), nullable=False),
        sa.Column("duplicate_hash", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "external_trade_id", name="uq_master_trade_event_session_trade"),
        sa.UniqueConstraint("session_id", "duplicate_hash", name="uq_master_trade_event_session_hash"),
    )

    op.create_table(
        "copied_trade_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "master_trade_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("master_trade_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("copy_group_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("copy_groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "copier_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("child_order_id", sa.String(length=120), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM("PENDING", "PLACED", "FAILED", "SKIPPED", name="copied_trade_order_status", create_type=False),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("master_trade_event_id", "copier_account_id", name="uq_copied_trade_order_event_account"),
    )
    op.create_index("ix_copy_sessions_master_account_id", "copy_sessions", ["master_account_id"])
    op.create_index("ix_master_trade_events_session_id", "master_trade_events", ["session_id"])
    op.create_index("ix_copied_trade_orders_master_trade_event_id", "copied_trade_orders", ["master_trade_event_id"])


def downgrade() -> None:
    op.drop_index("ix_copied_trade_orders_master_trade_event_id", table_name="copied_trade_orders")
    op.drop_index("ix_master_trade_events_session_id", table_name="master_trade_events")
    op.drop_index("ix_copy_sessions_master_account_id", table_name="copy_sessions")
    op.drop_table("copied_trade_orders")
    op.drop_table("master_trade_events")
    op.drop_table("copy_sessions")
    op.drop_column("copy_groups", "description")
    postgresql.ENUM(name="copied_trade_order_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="copy_session_status").drop(op.get_bind(), checkfirst=True)
