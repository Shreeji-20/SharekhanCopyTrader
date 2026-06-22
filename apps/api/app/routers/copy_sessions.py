import uuid
from collections import Counter

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.audit import add_audit_log
from app.core.config import get_settings
from app.dependencies import CurrentUser, DbSession
from app.models import (
    AccountType,
    BrokerAccount,
    CopiedTradeOrder,
    CopyGroup,
    CopyGroupMember,
    CopySession,
    CopySessionStatus,
    MasterTradeEvent,
    UserRole,
    utcnow,
)
from app.schemas import CopiedTradeOrderRead, CopySessionRead, CopySessionStart, MasterTradeEventRead
from app.services.broker_router import BrokerRouterClient
from app.services.live_copy import live_copy_manager

router = APIRouter(prefix="/copy-sessions", tags=["copy-sessions"])


async def _account_for_user(db: DbSession, account_id: uuid.UUID, current_user: CurrentUser) -> BrokerAccount:
    account = await db.get(BrokerAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if current_user.role != UserRole.ADMIN and account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


async def _session_for_user(db: DbSession, session_id: uuid.UUID, current_user: CurrentUser) -> CopySession:
    session = await db.get(CopySession, session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Copy session not found")
    await _account_for_user(db, session.master_account_id, current_user)
    return session


def _missing_master_fields(master: BrokerAccount) -> list[str]:
    return [
        label
        for label, value in (
            ("api_key", master.api_key),
            ("secret_key", master.secret_key),
            ("customer_id", master.customer_id),
            ("access_token", master.access_token),
        )
        if not value
    ]


async def _validate_start_payload(
    db: DbSession,
    payload: CopySessionStart,
    current_user: CurrentUser,
) -> tuple[BrokerAccount, list[uuid.UUID]]:
    master = await _account_for_user(db, payload.master_account_id, current_user)
    if master.account_type != AccountType.MASTER:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="master_account_id must be MASTER")
    if not master.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Master account is inactive")
    missing_master_fields = _missing_master_fields(master)
    if missing_master_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Master account is missing required fields: {', '.join(missing_master_fields)}",
        )
    existing_session = await db.scalar(
        select(CopySession).where(
            CopySession.master_account_id == master.id,
            CopySession.status.in_([CopySessionStatus.RUNNING, CopySessionStatus.PAUSED]),
        )
    )
    if existing_session:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This master account already has an active copy session. Resume or stop the existing session first.",
        )

    group_ids = list(dict.fromkeys(payload.copy_group_ids))
    groups = [
        await db.get(CopyGroup, group_id)
        for group_id in group_ids
    ]
    missing_group_ids = [str(group_id) for group_id, group in zip(group_ids, groups, strict=True) if group is None]
    if missing_group_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Copy groups not found: {', '.join(missing_group_ids)}")
    for group in groups:
        assert group is not None
        if group.master_account_id != master.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Copy group {group.name} does not belong to the selected master account",
            )
        if not group.is_active:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Copy group {group.name} is inactive")

    copy_account_ids = (
        await db.scalars(
            select(CopyGroupMember.copy_account_id).where(
                CopyGroupMember.copy_group_id.in_(group_ids),
                CopyGroupMember.is_enabled.is_(True),
            )
        )
    ).all()
    if not copy_account_ids:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Selected groups do not have enabled copy accounts")
    duplicate_account_ids = [account_id for account_id, count in Counter(copy_account_ids).items() if count > 1]
    if duplicate_account_ids and not payload.allow_duplicate_copiers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "One or more copy accounts appear in multiple selected groups. "
                "Run /copy-groups/validate for details or start with allow_duplicate_copiers=true to de-dupe by first group."
            ),
        )
    return master, group_ids


async def _connect_master_ws_or_mark_error(db: DbSession, session: CopySession) -> None:
    try:
        await BrokerRouterClient().ws_connect(session.master_account_id)
    except HTTPException as exc:
        session.status = CopySessionStatus.ERROR
        session.last_error = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await db.commit()
        raise


@router.post("/start", response_model=CopySessionRead, status_code=status.HTTP_201_CREATED)
async def start_copy_session(
    payload: CopySessionStart,
    db: DbSession,
    current_user: CurrentUser,
) -> CopySession:
    _, group_ids = await _validate_start_payload(db, payload, current_user)
    settings = get_settings()
    dry_run = settings.copy_trading_dry_run if payload.dry_run is None else payload.dry_run
    session = CopySession(
        master_account_id=payload.master_account_id,
        status=CopySessionStatus.RUNNING,
        active_group_ids=[str(group_id) for group_id in group_ids],
        dry_run=dry_run,
        created_by=current_user.id,
    )
    db.add(session)
    await db.flush()
    await add_audit_log(
        db,
        action="copy_session.start",
        entity_type="copy_session",
        entity_id=session.id,
        user_id=current_user.id,
        metadata={"master_account_id": str(payload.master_account_id), "group_ids": [str(group_id) for group_id in group_ids]},
    )
    await db.commit()
    await db.refresh(session)
    await live_copy_manager.preload_session_targets(session.id)
    await _connect_master_ws_or_mark_error(db, session)
    await live_copy_manager.start_session_task(session.id)
    return session


@router.get("", response_model=list[CopySessionRead])
async def list_copy_sessions(
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=25, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[CopySession]:
    statement = select(CopySession).join(BrokerAccount, BrokerAccount.id == CopySession.master_account_id)
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    sessions = await db.scalars(statement.order_by(CopySession.created_at.desc()).limit(limit).offset(offset))
    return list(sessions.all())


@router.get("/{session_id}", response_model=CopySessionRead)
async def get_copy_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> CopySession:
    return await _session_for_user(db, session_id, current_user)


@router.post("/{session_id}/pause", response_model=CopySessionRead)
async def pause_copy_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> CopySession:
    session = await _session_for_user(db, session_id, current_user)
    if session.status != CopySessionStatus.RUNNING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only RUNNING sessions can be paused")
    session.status = CopySessionStatus.PAUSED
    session.paused_at = utcnow()
    await add_audit_log(
        db,
        action="copy_session.pause",
        entity_type="copy_session",
        entity_id=session.id,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(session)
    live_copy_manager.invalidate_session_targets(session.id)
    return session


@router.post("/{session_id}/resume", response_model=CopySessionRead)
async def resume_copy_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> CopySession:
    session = await _session_for_user(db, session_id, current_user)
    if session.status != CopySessionStatus.PAUSED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only PAUSED sessions can be resumed")
    session.status = CopySessionStatus.RUNNING
    session.resumed_at = utcnow()
    session.last_error = None
    await add_audit_log(
        db,
        action="copy_session.resume",
        entity_type="copy_session",
        entity_id=session.id,
        user_id=current_user.id,
    )
    await db.commit()
    await db.refresh(session)
    await live_copy_manager.preload_session_targets(session.id)
    await _connect_master_ws_or_mark_error(db, session)
    await live_copy_manager.start_session_task(session.id)
    return session


@router.post("/{session_id}/stop", response_model=CopySessionRead)
async def stop_copy_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> CopySession:
    session = await _session_for_user(db, session_id, current_user)
    if session.status != CopySessionStatus.STOPPED:
        session.status = CopySessionStatus.STOPPED
        session.stopped_at = utcnow()
        await add_audit_log(
            db,
            action="copy_session.stop",
            entity_type="copy_session",
            entity_id=session.id,
            user_id=current_user.id,
        )
        await db.commit()
        await db.refresh(session)
        live_copy_manager.invalidate_session_targets(session.id)
    await live_copy_manager.stop_session_task(session.id)
    try:
        await BrokerRouterClient().ws_disconnect(session.master_account_id)
    except HTTPException as exc:
        session.last_error = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        await db.commit()
        await db.refresh(session)
    return session


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_copy_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> None:
    session = await _session_for_user(db, session_id, current_user)
    master_account_id = session.master_account_id
    if session.status in {CopySessionStatus.RUNNING, CopySessionStatus.PAUSED}:
        await live_copy_manager.stop_session_task(session.id)
        try:
            await BrokerRouterClient().ws_disconnect(master_account_id)
        except HTTPException:
            pass
    await db.delete(session)
    await add_audit_log(
        db,
        action="copy_session.delete",
        entity_type="copy_session",
        entity_id=session_id,
        user_id=current_user.id,
    )
    await db.commit()
    live_copy_manager.invalidate_session_targets(session_id)


@router.get("/{session_id}/stream-status")
async def get_session_stream_status(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    session = await _session_for_user(db, session_id, current_user)
    return await BrokerRouterClient().ws_status(session.master_account_id)


@router.get("/{session_id}/events", response_model=list[MasterTradeEventRead])
async def list_session_events(
    session_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[MasterTradeEvent]:
    await _session_for_user(db, session_id, current_user)
    events = await db.scalars(
        select(MasterTradeEvent)
        .where(MasterTradeEvent.session_id == session_id)
        .order_by(MasterTradeEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(events.all())


@router.get("/{session_id}/copied-orders", response_model=list[CopiedTradeOrderRead])
async def list_session_copied_orders(
    session_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
) -> list[CopiedTradeOrder]:
    await _session_for_user(db, session_id, current_user)
    copied_orders = await db.scalars(
        select(CopiedTradeOrder)
        .join(MasterTradeEvent, MasterTradeEvent.id == CopiedTradeOrder.master_trade_event_id)
        .where(MasterTradeEvent.session_id == session_id)
        .order_by(CopiedTradeOrder.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(copied_orders.all())
