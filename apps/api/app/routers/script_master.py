import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.models import BrokerAccount, UserRole
from app.services.script_master import script_master_service

router = APIRouter(prefix="/script-master", tags=["script-master"])


async def _account_for_user(db: DbSession, account_id: uuid.UUID, current_user: CurrentUser) -> BrokerAccount:
    account = await db.get(BrokerAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if current_user.role != UserRole.ADMIN and account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


@router.get("/{exchange}/status")
async def script_master_status(exchange: str, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    return await script_master_service.status(db, exchange)


@router.post("/{exchange}/refresh")
async def refresh_script_master(
    exchange: str,
    db: DbSession,
    current_user: CurrentUser,
    account_id: uuid.UUID = Query(..., description="Logged-in Sharekhan account used to fetch the master data"),
) -> dict[str, object]:
    await _account_for_user(db, account_id, current_user)
    result = await script_master_service.refresh_exchange(db, exchange, account_id)
    await add_audit_log(
        db,
        action="script_master.refresh",
        entity_type="script_master",
        entity_id=exchange.upper(),
        user_id=current_user.id,
        metadata={"account_id": str(account_id), "records": result["records"]},
    )
    await db.commit()
    return {
        "exchange": result["exchange"],
        "records": result["records"],
        "refreshed_at": result["refreshed_at"].isoformat(),
    }
