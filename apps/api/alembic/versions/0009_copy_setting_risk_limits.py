"""add copy setting risk limits

Revision ID: 0009_copy_setting_risk_limits
Revises: 0008_script_master_cache
Create Date: 2026-06-05 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0009_copy_setting_risk_limits"
down_revision: str | None = "0008_script_master_cache"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("copy_settings", sa.Column("min_qty", sa.Integer(), nullable=True))
    op.add_column("copy_settings", sa.Column("max_trades_per_day", sa.Integer(), nullable=True))
    op.add_column("copy_settings", sa.Column("max_daily_loss", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("copy_settings", "max_daily_loss")
    op.drop_column("copy_settings", "max_trades_per_day")
    op.drop_column("copy_settings", "min_qty")
