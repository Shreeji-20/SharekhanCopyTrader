"""add sharekhan login state lookup

Revision ID: 0006_sharekhan_login_state
Revises: 0005_sharekhan_request_token
Create Date: 2026-06-02 17:05:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision: str = "0006_sharekhan_login_state"
down_revision: str | None = "0005_sharekhan_request_token"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("broker_accounts", sa.Column("sharekhan_login_state", sa.String(length=32), nullable=True))
    op.create_index(
        "ix_broker_accounts_sharekhan_login_state",
        "broker_accounts",
        ["sharekhan_login_state"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_broker_accounts_sharekhan_login_state", table_name="broker_accounts")
    op.drop_column("broker_accounts", "sharekhan_login_state")
