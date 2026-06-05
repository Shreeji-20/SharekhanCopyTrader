"""make sharekhan identity fields optional

Revision ID: 0004_optional_sharekhan_identity
Revises: 0003_structured_proxy_fields
Create Date: 2026-06-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_optional_sharekhan_identity"
down_revision: str | None = "0003_structured_proxy_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("broker_accounts", "customer_id", existing_type=sa.String(length=80), nullable=True)
    op.alter_column("broker_accounts", "login_id", existing_type=sa.String(length=120), nullable=True)


def downgrade() -> None:
    op.alter_column("broker_accounts", "login_id", existing_type=sa.String(length=120), nullable=False)
    op.alter_column("broker_accounts", "customer_id", existing_type=sa.String(length=80), nullable=False)
