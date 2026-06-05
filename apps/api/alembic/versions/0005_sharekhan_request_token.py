"""add sharekhan request token storage

Revision ID: 0005_sharekhan_request_token
Revises: 0004_optional_sharekhan_identity
Create Date: 2026-06-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_sharekhan_request_token"
down_revision: str | None = "0004_optional_sharekhan_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("broker_accounts", sa.Column("request_token", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("broker_accounts", "request_token")
