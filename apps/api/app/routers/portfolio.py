from fastapi import APIRouter, Query
from sqlalchemy import or_, select

from app.dependencies import CurrentUser, DbSession
from app.models import BrokerAccount, Holding, Position, Trade, UserRole
from app.schemas import HoldingRead, PositionRead, TradeRead

router = APIRouter(tags=["portfolio"])


@router.get("/positions", response_model=list[PositionRead])
async def list_positions(
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Position]:
    statement = select(Position).join(BrokerAccount, BrokerAccount.id == Position.broker_account_id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    if search:
        like = f"%{search.upper()}%"
        statement = statement.where(or_(Position.trading_symbol.ilike(like), Position.scrip_code.ilike(like)))
    result = await db.scalars(statement.order_by(Position.synced_at.desc()).limit(limit).offset(offset))
    return list(result.all())


@router.get("/holdings", response_model=list[HoldingRead])
async def list_holdings(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Holding]:
    statement = select(Holding).join(BrokerAccount, BrokerAccount.id == Holding.broker_account_id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    result = await db.scalars(statement.order_by(Holding.synced_at.desc()).limit(limit).offset(offset))
    return list(result.all())


@router.get("/trades", response_model=list[TradeRead])
async def list_trades(
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = Query(default=None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[Trade]:
    statement = select(Trade).join(BrokerAccount, BrokerAccount.id == Trade.broker_account_id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    if search:
        like = f"%{search.upper()}%"
        statement = statement.where(or_(Trade.trading_symbol.ilike(like), Trade.broker_trade_id.ilike(like)))
    result = await db.scalars(statement.order_by(Trade.synced_at.desc()).limit(limit).offset(offset))
    return list(result.all())

