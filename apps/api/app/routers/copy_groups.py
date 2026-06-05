import uuid
from collections import defaultdict

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.models import AccountType, BrokerAccount, CopyGroup, CopyGroupMember, CopySetting, UserRole
from app.schemas import (
    CopyGroupAccountRead,
    CopyGroupCreate,
    CopyGroupDetailRead,
    CopyGroupMemberCreate,
    CopyGroupMemberDetailRead,
    CopyGroupMemberRead,
    CopyGroupMemberSettingRead,
    CopyGroupRead,
    CopyGroupUpdate,
    CopyGroupValidationRead,
    CopyGroupValidationRequest,
    DuplicateCopyAccountWarning,
)

router = APIRouter(prefix="/copy-groups", tags=["copy-groups"])


async def _account_for_user(db: DbSession, account_id: uuid.UUID, current_user: CurrentUser) -> BrokerAccount:
    account = await db.get(BrokerAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if current_user.role != UserRole.ADMIN and account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


async def _group_for_user(db: DbSession, group_id: uuid.UUID, current_user: CurrentUser) -> CopyGroup:
    group = await db.get(CopyGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copy group not found")
    master = await db.get(BrokerAccount, group.master_account_id)
    if current_user.role != UserRole.ADMIN and master and master.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return group


def _account_summary(account: BrokerAccount) -> CopyGroupAccountRead:
    return CopyGroupAccountRead(
        id=account.id,
        account_name=account.account_name,
        account_type=account.account_type,
        customer_id=account.customer_id,
        login_id=account.login_id,
        is_active=account.is_active,
    )


async def _group_detail(db: DbSession, group: CopyGroup) -> CopyGroupDetailRead:
    master = await db.get(BrokerAccount, group.master_account_id)
    rows = (
        await db.execute(
            select(CopyGroupMember, BrokerAccount, CopySetting)
            .join(BrokerAccount, BrokerAccount.id == CopyGroupMember.copy_account_id)
            .outerjoin(
                CopySetting,
                (CopySetting.copy_group_id == CopyGroupMember.copy_group_id)
                & (CopySetting.copy_account_id == CopyGroupMember.copy_account_id),
            )
            .where(CopyGroupMember.copy_group_id == group.id)
            .order_by(BrokerAccount.account_name.asc())
        )
    ).all()
    members = [
        CopyGroupMemberDetailRead(
            id=member.id,
            copy_group_id=member.copy_group_id,
            copy_account_id=member.copy_account_id,
            copy_account=_account_summary(copy_account),
            copy_setting=CopyGroupMemberSettingRead.model_validate(setting) if setting else None,
            is_enabled=member.is_enabled,
            created_at=member.created_at,
        )
        for member, copy_account, setting in rows
    ]
    return CopyGroupDetailRead(
        id=group.id,
        name=group.name,
        description=group.description,
        master_account_id=group.master_account_id,
        master_account_name=master.account_name if master else None,
        is_active=group.is_active,
        created_at=group.created_at,
        updated_at=group.updated_at,
        members=members,
    )


@router.get("", response_model=list[CopyGroupRead])
async def list_copy_groups(db: DbSession, current_user: CurrentUser) -> list[CopyGroup]:
    statement = select(CopyGroup).join(BrokerAccount, BrokerAccount.id == CopyGroup.master_account_id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    return list((await db.scalars(statement.order_by(CopyGroup.created_at.desc()))).all())


@router.post("", response_model=CopyGroupRead, status_code=status.HTTP_201_CREATED)
async def create_copy_group(payload: CopyGroupCreate, db: DbSession, current_user: CurrentUser) -> CopyGroup:
    master = await _account_for_user(db, payload.master_account_id, current_user)
    if master.account_type != AccountType.MASTER:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="master_account_id must be MASTER")
    group = CopyGroup(
        name=payload.name,
        description=payload.description,
        master_account_id=payload.master_account_id,
        is_active=payload.is_active,
    )
    db.add(group)
    await db.flush()
    await add_audit_log(
        db,
        action="copy_group.create",
        entity_type="copy_group",
        entity_id=group.id,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(group)
    return group


@router.post("/validate", response_model=CopyGroupValidationRead)
async def validate_copy_groups(
    payload: CopyGroupValidationRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> CopyGroupValidationRead:
    master = await _account_for_user(db, payload.master_account_id, current_user)
    warnings: list[str] = []
    if master.account_type != AccountType.MASTER:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="master_account_id must be MASTER")
    if not master.is_active:
        warnings.append(f"Master account {master.account_name} is inactive.")
    if not master.customer_id:
        warnings.append(f"Master account {master.account_name} is missing customer id.")
    if not master.access_token:
        warnings.append(f"Master account {master.account_name} is not logged in with an access token.")

    group_ids = list(dict.fromkeys(payload.copy_group_ids))
    groups = [
        await _group_for_user(db, group_id, current_user)
        for group_id in group_ids
    ]
    for group in groups:
        if group.master_account_id != master.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Copy group {group.name} does not belong to the selected master account.",
            )
        if not group.is_active:
            warnings.append(f"Copy group {group.name} is inactive.")

    rows = (
        await db.execute(
            select(CopyGroupMember, BrokerAccount)
            .join(BrokerAccount, BrokerAccount.id == CopyGroupMember.copy_account_id)
            .where(CopyGroupMember.copy_group_id.in_(group_ids), CopyGroupMember.is_enabled.is_(True))
        )
    ).all()
    copy_group_ids_by_account: defaultdict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    copy_account_names: dict[uuid.UUID, str] = {}
    for member, copy_account in rows:
        copy_group_ids_by_account[copy_account.id].append(member.copy_group_id)
        copy_account_names[copy_account.id] = copy_account.account_name
        if not copy_account.is_active:
            warnings.append(f"Copy account {copy_account.account_name} is inactive.")
        if not copy_account.customer_id:
            warnings.append(f"Copy account {copy_account.account_name} is missing customer id.")
        if not copy_account.login_id:
            warnings.append(f"Copy account {copy_account.account_name} is missing login id.")
        if not copy_account.api_key:
            warnings.append(f"Copy account {copy_account.account_name} is missing API key.")
        if not copy_account.secret_key:
            warnings.append(f"Copy account {copy_account.account_name} is missing secret key.")
        if not copy_account.access_token:
            warnings.append(f"Copy account {copy_account.account_name} is not logged in with an access token.")

    duplicate_copy_accounts = [
        DuplicateCopyAccountWarning(
            copy_account_id=copy_account_id,
            account_name=copy_account_names[copy_account_id],
            copy_group_ids=duplicate_group_ids,
        )
        for copy_account_id, duplicate_group_ids in copy_group_ids_by_account.items()
        if len(duplicate_group_ids) > 1
    ]
    for duplicate in duplicate_copy_accounts:
        warnings.append(f"Copy account {duplicate.account_name} appears in multiple selected groups.")
    if not rows:
        warnings.append("No enabled copy accounts were found in the selected groups.")
    return CopyGroupValidationRead(
        ok=not warnings,
        warnings=warnings,
        duplicate_copy_accounts=duplicate_copy_accounts,
        copy_account_count=len(copy_group_ids_by_account),
    )


@router.get("/{group_id}", response_model=CopyGroupDetailRead)
async def get_copy_group(group_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> CopyGroupDetailRead:
    return await _group_detail(db, await _group_for_user(db, group_id, current_user))


@router.patch("/{group_id}", response_model=CopyGroupRead)
async def update_copy_group(
    group_id: uuid.UUID,
    payload: CopyGroupUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> CopyGroup:
    group = await _group_for_user(db, group_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    if "master_account_id" in data:
        master = await _account_for_user(db, data["master_account_id"], current_user)
        if master.account_type != AccountType.MASTER:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="master_account_id must be MASTER")
    for field, value in data.items():
        setattr(group, field, value)
    await add_audit_log(
        db,
        action="copy_group.update",
        entity_type="copy_group",
        entity_id=group.id,
        user_id=current_user.id,
        metadata={"fields": sorted(data.keys())},
    )
    await db.commit()
    await db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_copy_group(group_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    group = await _group_for_user(db, group_id, current_user)
    await db.delete(group)
    await add_audit_log(
        db,
        action="copy_group.delete",
        entity_type="copy_group",
        entity_id=group_id,
        user_id=current_user.id,
    )
    await db.commit()


@router.post("/{group_id}/members", response_model=CopyGroupMemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    group_id: uuid.UUID,
    payload: CopyGroupMemberCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> CopyGroupMember:
    group = await _group_for_user(db, group_id, current_user)
    copy_account = await _account_for_user(db, payload.copy_account_id, current_user)
    if copy_account.account_type != AccountType.COPY:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="copy_account_id must be COPY")
    existing = await db.scalar(
        select(CopyGroupMember).where(
            CopyGroupMember.copy_group_id == group.id,
            CopyGroupMember.copy_account_id == copy_account.id,
        )
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Copy account already in group")
    member = CopyGroupMember(copy_group_id=group.id, copy_account_id=copy_account.id, is_enabled=payload.is_enabled)
    db.add(member)
    db.add(CopySetting(copy_group_id=group.id, copy_account_id=copy_account.id))
    await db.flush()
    await add_audit_log(
        db,
        action="copy_group.member_add",
        entity_type="copy_group_member",
        entity_id=member.id,
        user_id=current_user.id,
        metadata={"copy_group_id": str(group.id), "copy_account_id": str(copy_account.id)},
    )
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{group_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    group_id: uuid.UUID,
    member_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    await _group_for_user(db, group_id, current_user)
    member = await db.get(CopyGroupMember, member_id)
    if not member or member.copy_group_id != group_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    await db.delete(member)
    await add_audit_log(
        db,
        action="copy_group.member_remove",
        entity_type="copy_group_member",
        entity_id=member_id,
        user_id=current_user.id,
    )
    await db.commit()
