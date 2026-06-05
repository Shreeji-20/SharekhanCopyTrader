"""add broker account proxy url

Revision ID: 0002_broker_account_proxy_url
Revises: 0001_initial_schema
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_broker_account_proxy_url"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("broker_accounts", sa.Column("proxy_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_accounts", "proxy_url")
