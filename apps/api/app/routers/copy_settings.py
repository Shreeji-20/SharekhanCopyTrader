import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.models import AccountType, BrokerAccount, CopySetting, UserRole
from app.schemas import CopySettingPatch, CopySettingRead

router = APIRouter(prefix="/copy-settings", tags=["copy-settings"])


async def _copy_account_for_user(db: DbSession, copy_account_id: uuid.UUID, current_user: CurrentUser) -> BrokerAccount:
    account = await db.get(BrokerAccount, copy_account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copy account not found")
    if current_user.role != UserRole.ADMIN and account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    if account.account_type != AccountType.COPY:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Account must be COPY")
    return account


async def _load_setting(
    db: DbSession,
    copy_account_id: uuid.UUID,
    copy_group_id: uuid.UUID | None,
) -> CopySetting | None:
    statement = select(CopySetting).where(CopySetting.copy_account_id == copy_account_id)
    if copy_group_id:
        statement = statement.where(CopySetting.copy_group_id == copy_group_id)
    return await db.scalar(statement.order_by(CopySetting.id))


@router.get("/{copy_account_id}", response_model=CopySettingRead)
async def get_copy_setting(
    copy_account_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    copy_group_id: uuid.UUID | None = Query(default=None),
) -> CopySetting:
    await _copy_account_for_user(db, copy_account_id, current_user)
    setting = await _load_setting(db, copy_account_id, copy_group_id)
    if not setting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copy settings not found")
    return setting


@router.patch("/{copy_account_id}", response_model=CopySettingRead)
async def patch_copy_setting(
    copy_account_id: uuid.UUID,
    payload: CopySettingPatch,
    db: DbSession,
    current_user: CurrentUser,
    copy_group_id: uuid.UUID | None = Query(default=None),
) -> CopySetting:
    await _copy_account_for_user(db, copy_account_id, current_user)
    group_id = payload.copy_group_id or copy_group_id
    setting = await _load_setting(db, copy_account_id, group_id)
    if not setting:
        if not group_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="copy_group_id is required to create copy settings",
            )
        setting = CopySetting(copy_account_id=copy_account_id, copy_group_id=group_id)
        db.add(setting)
    data = payload.model_dump(exclude_unset=True, exclude={"copy_group_id"})
    for field, value in data.items():
        setattr(setting, field, value)
    await add_audit_log(
        db,
        action="copy_setting.update",
        entity_type="copy_setting",
        entity_id=setting.id,
        user_id=current_user.id,
        metadata={"copy_account_id": str(copy_account_id), "fields": sorted(data.keys())},
    )
    await db.commit()
    await db.refresh(setting)
    return setting

