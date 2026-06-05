"""add script master cache

Revision ID: 0008_script_master_cache
Revises: 0007_live_copy_trading
Create Date: 2026-06-05 10:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0008_script_master_cache"
down_revision: str | None = "0007_live_copy_trading"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "script_master_instruments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("exchange", sa.String(length=20), nullable=False),
        sa.Column("segment", sa.String(length=40), nullable=True),
        sa.Column("scrip_code", sa.String(length=40), nullable=False),
        sa.Column("trading_symbol", sa.String(length=120), nullable=False),
        sa.Column("symbol_name", sa.String(length=255), nullable=True),
        sa.Column("underlying_symbol", sa.String(length=120), nullable=True),
        sa.Column("instrument_type", sa.String(length=40), nullable=True),
        sa.Column("option_type", sa.String(length=10), nullable=True),
        sa.Column("strike_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("expiry_date", sa.Date(), nullable=True),
        sa.Column("lot_size", sa.Integer(), nullable=True),
        sa.Column("isin", sa.String(length=32), nullable=True),
        sa.Column("raw_payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("exchange", "scrip_code", name="uq_script_master_exchange_scrip_code"),
    )
    op.create_index("ix_script_master_exchange_symbol", "script_master_instruments", ["exchange", "trading_symbol"])
    op.create_index(
        "ix_script_master_exchange_segment_symbol",
        "script_master_instruments",
        ["exchange", "segment", "trading_symbol"],
    )
    op.create_index(
        "ix_script_master_derivative_lookup",
        "script_master_instruments",
        ["exchange", "instrument_type", "trading_symbol", "expiry_date", "strike_price", "option_type"],
    )
    op.create_index("ix_script_master_underlying_symbol", "script_master_instruments", ["underlying_symbol"])
    op.create_index("ix_script_master_isin", "script_master_instruments", ["isin"])


def downgrade() -> None:
    op.drop_index("ix_script_master_isin", table_name="script_master_instruments")
    op.drop_index("ix_script_master_underlying_symbol", table_name="script_master_instruments")
    op.drop_index("ix_script_master_derivative_lookup", table_name="script_master_instruments")
    op.drop_index("ix_script_master_exchange_segment_symbol", table_name="script_master_instruments")
    op.drop_index("ix_script_master_exchange_symbol", table_name="script_master_instruments")
    op.drop_table("script_master_instruments")
