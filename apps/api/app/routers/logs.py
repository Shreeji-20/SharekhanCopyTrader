from fastapi import APIRouter, Query
from sqlalchemy import select

from app.dependencies import CurrentUser, DbSession
from app.models import AuditLog, UserRole
from app.schemas import AuditLogRead

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[AuditLogRead])
async def list_logs(
    db: DbSession,
    current_user: CurrentUser,
    action: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLog]:
    statement = select(AuditLog)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(AuditLog.user_id == current_user.id)
    if action:
        statement = statement.where(AuditLog.action.ilike(f"%{action}%"))
    result = await db.scalars(statement.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset))
    return list(result.all())

