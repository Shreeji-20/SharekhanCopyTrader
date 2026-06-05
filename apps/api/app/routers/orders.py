from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.dependencies import CurrentUser, DbSession
from app.models import BrokerAccount, CopyOrder, MasterOrder, UserRole
from app.schemas import CopyOrderRead, MasterOrderRead

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/master", response_model=list[MasterOrderRead])
async def list_master_orders(
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[MasterOrder]:
    statement = select(MasterOrder).join(BrokerAccount, BrokerAccount.id == MasterOrder.master_account_id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    if search:
        like = f"%{search.upper()}%"
        statement = statement.where(
            or_(MasterOrder.trading_symbol.ilike(like), MasterOrder.broker_order_id.ilike(like))
        )
    if status:
        statement = statement.where(MasterOrder.status == status)
    result = await db.scalars(statement.order_by(MasterOrder.created_at.desc()).limit(limit).offset(offset))
    return list(result.all())


@router.get("/copy", response_model=list[CopyOrderRead])
async def list_copy_orders(
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[CopyOrder]:
    statement = (
        select(CopyOrder)
        .join(BrokerAccount, BrokerAccount.id == CopyOrder.copy_account_id)
        .join(MasterOrder, MasterOrder.id == CopyOrder.master_order_id)
    )
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    if search:
        like = f"%{search.upper()}%"
        statement = statement.where(
            or_(
                MasterOrder.trading_symbol.ilike(like),
                CopyOrder.broker_order_id.ilike(like),
                CopyOrder.idempotency_key.ilike(like),
            )
        )
    if status:
        statement = statement.where(CopyOrder.status == status)
    result = await db.scalars(statement.order_by(CopyOrder.created_at.desc()).limit(limit).offset(offset))
    return list(result.all())

