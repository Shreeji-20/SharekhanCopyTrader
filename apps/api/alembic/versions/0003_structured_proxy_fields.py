"""replace proxy url with structured proxy fields

Revision ID: 0003_structured_proxy_fields
Revises: 0002_broker_account_proxy_url
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_structured_proxy_fields"
down_revision: str | None = "0002_broker_account_proxy_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("broker_accounts", sa.Column("proxy_scheme", sa.String(length=10), nullable=True))
    op.add_column("broker_accounts", sa.Column("proxy_host", sa.Text(), nullable=True))
    op.add_column("broker_accounts", sa.Column("proxy_port", sa.Integer(), nullable=True))
    op.add_column("broker_accounts", sa.Column("proxy_username", sa.Text(), nullable=True))
    op.add_column("broker_accounts", sa.Column("proxy_password", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_accounts", "proxy_password")
    op.drop_column("broker_accounts", "proxy_username")
    op.drop_column("broker_accounts", "proxy_port")
    op.drop_column("broker_accounts", "proxy_host")
    op.drop_column("broker_accounts", "proxy_scheme")
