from datetime import datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from app.dependencies import CurrentUser, DbSession
from app.models import AccountType, BrokerAccount, CopyOrder, CopyOrderStatus, MasterOrder, Position, UserRole
from app.schemas import DashboardMetrics

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics", response_model=DashboardMetrics)
async def dashboard_metrics(db: DbSession, current_user: CurrentUser) -> DashboardMetrics:
    start_of_day = datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)

    account_filter = True
    if current_user.role != UserRole.ADMIN:
        account_filter = BrokerAccount.user_id == current_user.id

    master_orders_today = await db.scalar(
        select(func.count(MasterOrder.id))
        .join(BrokerAccount, BrokerAccount.id == MasterOrder.master_account_id)
        .where(account_filter, MasterOrder.created_at >= start_of_day)
    )
    successful_copied = await db.scalar(
        select(func.count(CopyOrder.id))
        .join(BrokerAccount, BrokerAccount.id == CopyOrder.copy_account_id)
        .where(account_filter, CopyOrder.status == CopyOrderStatus.SUCCESS)
    )
    failed_copy = await db.scalar(
        select(func.count(CopyOrder.id))
        .join(BrokerAccount, BrokerAccount.id == CopyOrder.copy_account_id)
        .where(account_filter, CopyOrder.status == CopyOrderStatus.FAILED)
    )
    active_copy_accounts = await db.scalar(
        select(func.count(BrokerAccount.id)).where(
            account_filter,
            BrokerAccount.account_type == AccountType.COPY,
            BrokerAccount.is_active.is_(True),
        )
    )
    open_positions = await db.scalar(
        select(func.count(Position.id))
        .join(BrokerAccount, BrokerAccount.id == Position.broker_account_id)
        .where(account_filter, Position.quantity != 0)
    )
    total_pnl = await db.scalar(
        select(func.coalesce(func.sum(Position.pnl), 0))
        .join(BrokerAccount, BrokerAccount.id == Position.broker_account_id)
        .where(account_filter)
    )
    active_accounts = await db.scalar(
        select(func.count(BrokerAccount.id)).where(account_filter, BrokerAccount.is_active.is_(True))
    )
    connected_accounts = await db.scalar(
        select(func.count(BrokerAccount.id)).where(
            account_filter,
            BrokerAccount.is_active.is_(True),
            BrokerAccount.access_token.is_not(None),
        )
    )
    if not active_accounts:
        status = "DISCONNECTED"
    elif connected_accounts == active_accounts:
        status = "CONNECTED"
    elif connected_accounts:
        status = "DEGRADED"
    else:
        status = "DISCONNECTED"

    return DashboardMetrics(
        master_orders_today=master_orders_today or 0,
        successful_copied_orders=successful_copied or 0,
        failed_copy_orders=failed_copy or 0,
        active_copy_accounts=active_copy_accounts or 0,
        open_positions=open_positions or 0,
        total_pnl=Decimal(total_pnl or 0),
        broker_connection_status=status,
    )

