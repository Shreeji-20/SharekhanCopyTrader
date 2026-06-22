import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.models import AccountType, BrokerAccount, CopyGroup, CopyGroupMember, CopySetting, UserRole
from app.schemas import CopySettingPatch, CopySettingRead
from app.services.live_copy import live_copy_manager

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


async def _group_for_user(db: DbSession, copy_group_id: uuid.UUID, current_user: CurrentUser) -> CopyGroup:
    group = await db.get(CopyGroup, copy_group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copy group not found")
    master = await db.get(BrokerAccount, group.master_account_id)
    if current_user.role != UserRole.ADMIN and master and master.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return group


async def _require_member(db: DbSession, copy_account_id: uuid.UUID, copy_group_id: uuid.UUID) -> None:
    member = await db.scalar(
        select(CopyGroupMember).where(
            CopyGroupMember.copy_account_id == copy_account_id,
            CopyGroupMember.copy_group_id == copy_group_id,
        )
    )
    if not member:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copy account is not a member of this group")


async def _load_setting(
    db: DbSession,
    copy_account_id: uuid.UUID,
    copy_group_id: uuid.UUID,
) -> CopySetting | None:
    return await db.scalar(
        select(CopySetting).where(
            CopySetting.copy_account_id == copy_account_id,
            CopySetting.copy_group_id == copy_group_id,
        )
    )


@router.get("/{copy_account_id}", response_model=CopySettingRead)
async def get_copy_setting(
    copy_account_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    copy_group_id: uuid.UUID | None = Query(default=None),
) -> CopySetting:
    await _copy_account_for_user(db, copy_account_id, current_user)
    if copy_group_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="copy_group_id is required because copy settings are scoped to a copy group",
        )
    await _group_for_user(db, copy_group_id, current_user)
    await _require_member(db, copy_account_id, copy_group_id)
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
    if group_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="copy_group_id is required because copy settings are scoped to a copy group",
        )
    group = await _group_for_user(db, group_id, current_user)
    await _require_member(db, copy_account_id, group_id)
    setting = await _load_setting(db, copy_account_id, group_id)
    if not setting:
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
    live_copy_manager.invalidate_master_targets(group.master_account_id)
    await db.refresh(setting)
    return setting
