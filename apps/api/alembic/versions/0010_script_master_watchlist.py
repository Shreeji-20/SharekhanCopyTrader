"""add script master watchlist

Revision ID: 0010_script_master_watchlist
Revises: 0009_copy_setting_risk_limits
Create Date: 2026-06-17 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0010_script_master_watchlist"
down_revision: str | None = "0009_copy_setting_risk_limits"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("script_master_instruments", sa.Column("tick_size", sa.Numeric(18, 6), nullable=True))
    op.create_table(
        "script_master_watchlist_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("broker_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("scrip_code", sa.String(length=40), nullable=False),
        sa.Column("instrument_snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "account_id", "exchange", "scrip_code", name="uq_script_master_watchlist_user_account_scrip"),
    )
    op.create_index(
        "ix_script_master_watchlist_user_account",
        "script_master_watchlist_items",
        ["user_id", "account_id"],
    )
    op.create_index(
        "ix_script_master_watchlist_exchange_scrip",
        "script_master_watchlist_items",
        ["exchange", "scrip_code"],
    )


def downgrade() -> None:
    op.drop_index("ix_script_master_watchlist_exchange_scrip", table_name="script_master_watchlist_items")
    op.drop_index("ix_script_master_watchlist_user_account", table_name="script_master_watchlist_items")
    op.drop_table("script_master_watchlist_items")
    op.drop_column("script_master_instruments", "tick_size")
