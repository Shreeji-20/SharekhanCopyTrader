import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def add_audit_log(
    db: AsyncSession,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id else None,
            metadata_=metadata or {},
        )
    )

