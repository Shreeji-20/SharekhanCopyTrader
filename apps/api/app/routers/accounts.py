import secrets
import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.encryption import decrypt_secret, encrypt_secret
from app.models import BrokerAccount, CopyGroup, CopyGroupMember, CopySession, CopySessionStatus, UserRole
from app.schemas import (
    BrokerAccountCreate,
    BrokerAccountRead,
    BrokerAccountUpdate,
    SharekhanCallbackExchange,
    SharekhanOrderPayload,
    SharekhanTokenExchange,
    SharekhanWsSubscription,
)
from app.security import mask_secret
from app.services.broker_router import BrokerRouterClient
from app.services.live_copy import live_copy_manager
from app.services.script_master_preload import scheduled_login_preload_exchanges, warm_script_master_after_login

router = APIRouter(prefix="/accounts", tags=["accounts"])


async def create_sharekhan_state(db: DbSession) -> str:
    for _ in range(10):
        state = str(secrets.randbelow(90_000_000) + 10_000_000)
        existing = await db.scalar(select(BrokerAccount.id).where(BrokerAccount.sharekhan_login_state == state))
        if existing is None:
            return state
    return str(secrets.randbelow(9_000_000_000_000) + 1_000_000_000_000)


def safe_decrypt_secret(value: str | None) -> tuple[str | None, bool]:
    if value is None:
        return None, True
    try:
        return decrypt_secret(value), True
    except Exception:
        return None, False


def account_response(account: BrokerAccount) -> BrokerAccountRead:
    api_key, api_key_readable = safe_decrypt_secret(account.api_key)
    secret_key, secret_key_readable = safe_decrypt_secret(account.secret_key)
    vendor_key, vendor_key_readable = safe_decrypt_secret(account.vendor_key)
    proxy_host, proxy_host_readable = safe_decrypt_secret(account.proxy_host)
    proxy_username, proxy_username_readable = safe_decrypt_secret(account.proxy_username)
    proxy_password, proxy_password_readable = safe_decrypt_secret(account.proxy_password)
    request_token, request_token_readable = safe_decrypt_secret(account.request_token)
    access_token, access_token_readable = safe_decrypt_secret(account.access_token)
    refresh_token, refresh_token_readable = safe_decrypt_secret(account.refresh_token)
    credentials_readable = all(
        (
            api_key_readable,
            secret_key_readable,
            vendor_key_readable,
            proxy_host_readable,
            proxy_username_readable,
            proxy_password_readable,
            request_token_readable,
            access_token_readable,
            refresh_token_readable,
        )
    )
    return BrokerAccountRead(
        id=account.id,
        broker=account.broker,
        account_name=account.account_name,
        customer_id=account.customer_id,
        login_id=account.login_id,
        api_key=mask_secret(api_key) or ("UNREADABLE" if not api_key_readable else ""),
        secret_key=mask_secret(secret_key) or ("UNREADABLE" if not secret_key_readable else ""),
        vendor_key=mask_secret(vendor_key) or ("UNREADABLE" if not vendor_key_readable else None),
        proxy_scheme=account.proxy_scheme,
        proxy_host=proxy_host if proxy_host_readable else "UNREADABLE",
        proxy_port=account.proxy_port,
        proxy_username=proxy_username if proxy_username_readable else "UNREADABLE",
        proxy_password=mask_secret(proxy_password) or ("UNREADABLE" if not proxy_password_readable else None),
        request_token=mask_secret(request_token) if request_token_readable else None,
        access_token=mask_secret(access_token) if access_token_readable else None,
        refresh_token=mask_secret(refresh_token) if refresh_token_readable else None,
        token_expires_at=account.token_expires_at,
        credentials_readable=credentials_readable,
        account_type=account.account_type,
        is_active=account.is_active,
        last_connected_at=account.last_connected_at,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def stored_sharekhan_profile_response(account: BrokerAccount) -> dict[str, object]:
    request_token, request_token_readable = safe_decrypt_secret(account.request_token)
    access_token, access_token_readable = safe_decrypt_secret(account.access_token)
    refresh_token, refresh_token_readable = safe_decrypt_secret(account.refresh_token)
    readable = request_token_readable and access_token_readable and refresh_token_readable
    return {
        "ok": bool(access_token) and readable,
        "account_id": str(account.id),
        "access_token": mask_secret(access_token) if access_token_readable else None,
        "refresh_token": mask_secret(refresh_token) if refresh_token_readable else None,
        "customer_id": account.customer_id,
        "login_id": account.login_id,
        "full_name": None,
        "broker": account.broker.value,
        "exchanges": [],
        "token_expires_at": account.token_expires_at.isoformat() if account.token_expires_at else None,
        "raw_status": "stored",
        "raw_message": "Stored Sharekhan login details",
        "request_token_saved": bool(request_token) and request_token_readable,
    }


async def load_account(db: DbSession, account_id: uuid.UUID, current_user: CurrentUser) -> BrokerAccount:
    account = await db.get(BrokerAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if current_user.role != UserRole.ADMIN and account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


async def disconnect_account_stream(account_id: uuid.UUID) -> None:
    try:
        await BrokerRouterClient().ws_disconnect(account_id)
    except Exception:
        pass


@router.get("", response_model=list[BrokerAccountRead])
async def list_accounts(db: DbSession, current_user: CurrentUser) -> list[BrokerAccountRead]:
    statement = select(BrokerAccount).order_by(BrokerAccount.created_at.desc())
    if current_user.role != UserRole.ADMIN:
        statement = statement.where(BrokerAccount.user_id == current_user.id)
    accounts = (await db.scalars(statement)).all()
    return [account_response(account) for account in accounts]


@router.post("", response_model=BrokerAccountRead, status_code=status.HTTP_201_CREATED)
async def create_account(payload: BrokerAccountCreate, db: DbSession, current_user: CurrentUser) -> BrokerAccountRead:
    account = BrokerAccount(
        user_id=current_user.id,
        account_name=payload.account_name,
        customer_id=payload.customer_id,
        login_id=payload.login_id,
        api_key=encrypt_secret(payload.api_key) or "",
        secret_key=encrypt_secret(payload.secret_key) or "",
        vendor_key=encrypt_secret(payload.vendor_key),
        proxy_scheme=payload.proxy_scheme,
        proxy_host=encrypt_secret(payload.proxy_host),
        proxy_port=payload.proxy_port,
        proxy_username=encrypt_secret(payload.proxy_username),
        proxy_password=encrypt_secret(payload.proxy_password),
        account_type=payload.account_type,
    )
    db.add(account)
    await db.flush()
    await add_audit_log(
        db,
        action="broker_account.create",
        entity_type="broker_account",
        entity_id=account.id,
        user_id=current_user.id,
        metadata={"account_type": payload.account_type.value},
    )
    await db.commit()
    await db.refresh(account)
    return account_response(account)


@router.post("/sharekhan/callback")
async def sharekhan_callback(
    payload: SharekhanCallbackExchange,
    background_tasks: BackgroundTasks,
    db: DbSession,
) -> dict[str, object]:
    account: BrokerAccount | None = None
    if payload.state:
        account = await db.scalar(
            select(BrokerAccount).where(BrokerAccount.sharekhan_login_state == payload.state)
        )
    if account is None and payload.account_id:
        account = await db.get(BrokerAccount, payload.account_id)
    if account is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Sharekhan returned a request token, but the account could not be identified. Start account-wise login again from Accounts.",
        )

    account.request_token = encrypt_secret(payload.request_token)
    if payload.state:
        account.sharekhan_login_state = payload.state
    account.access_token = None
    account.refresh_token = None
    account.token_expires_at = None
    account.last_connected_at = None
    await add_audit_log(
        db,
        action="broker_account.request_token_update",
        entity_type="broker_account",
        entity_id=account.id,
        user_id=account.user_id,
    )
    await db.commit()
    result = await BrokerRouterClient().exchange_token(account.id, payload.request_token)
    await add_audit_log(
        db,
        action="broker_account.token_update",
        entity_type="broker_account",
        entity_id=account.id,
        user_id=account.user_id,
        metadata={"source": "sharekhan_callback"},
    )
    await db.commit()
    preload_exchanges = scheduled_login_preload_exchanges(result) if result.get("ok", True) else []
    if preload_exchanges:
        background_tasks.add_task(warm_script_master_after_login, account.id, result)
    return {
        "ok": bool(result.get("ok", True)),
        "account_id": str(account.id),
        "request_token_saved": True,
        "access_token_generated": bool(result.get("ok", True)),
        "profile": result,
        "script_master_preload": {
            "scheduled": bool(preload_exchanges),
            "exchanges": preload_exchanges,
        },
    }


@router.get("/{account_id}", response_model=BrokerAccountRead)
async def get_account(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> BrokerAccountRead:
    return account_response(await load_account(db, account_id, current_user))


@router.patch("/{account_id}", response_model=BrokerAccountRead)
async def update_account(
    account_id: uuid.UUID,
    payload: BrokerAccountUpdate,
    db: DbSession,
    current_user: CurrentUser,
) -> BrokerAccountRead:
    account = await load_account(db, account_id, current_user)
    data = payload.model_dump(exclude_unset=True)
    credentials_changed = bool({"api_key", "secret_key", "vendor_key"} & data.keys())
    for field in ("api_key", "secret_key", "vendor_key", "proxy_host", "proxy_username", "proxy_password"):
        if field in data:
            setattr(account, field, encrypt_secret(data.pop(field)))
    if credentials_changed:
        account.sharekhan_login_state = None
        account.request_token = None
        account.access_token = None
        account.refresh_token = None
        account.token_expires_at = None
        account.last_connected_at = None
    for field, value in data.items():
        setattr(account, field, value)
    await add_audit_log(
        db,
        action="broker_account.update",
        entity_type="broker_account",
        entity_id=account.id,
        user_id=current_user.id,
        metadata={"fields": sorted(payload.model_dump(exclude_unset=True).keys())},
    )
    await db.commit()
    await db.refresh(account)
    return account_response(account)


@router.delete("/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_account(
    account_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    account = await load_account(db, account_id, current_user)
    master_ids = {
        account.id,
        *(
            await db.scalars(
                select(CopyGroup.master_account_id)
                .join(CopyGroupMember, CopyGroupMember.copy_group_id == CopyGroup.id)
                .where(CopyGroupMember.copy_account_id == account.id)
            )
        ).all(),
    }
    running_session_ids = (
        await db.scalars(
            select(CopySession.id).where(
                CopySession.master_account_id == account.id,
                CopySession.status.in_([CopySessionStatus.RUNNING, CopySessionStatus.PAUSED]),
            )
        )
    ).all()
    for session_id in running_session_ids:
        await live_copy_manager.stop_session_task(session_id)
    await db.execute(delete(CopyGroup).where(CopyGroup.master_account_id == account.id))
    await db.execute(delete(BrokerAccount).where(BrokerAccount.id == account.id))
    await add_audit_log(
        db,
        action="broker_account.delete",
        entity_type="broker_account",
        entity_id=account_id,
        user_id=current_user.id,
        metadata={
            "account_type": account.account_type.value,
            "stopped_sessions": [str(session_id) for session_id in running_session_ids],
        },
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account could not be deleted because related trading records still reference it.",
        ) from exc
    for master_id in master_ids:
        live_copy_manager.invalidate_master_targets(master_id)
    background_tasks.add_task(disconnect_account_stream, account_id)


@router.post("/{account_id}/sharekhan/login-url")
async def sharekhan_login_url(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    account = await load_account(db, account_id, current_user)
    state = await create_sharekhan_state(db)
    result = await BrokerRouterClient().login_url(account_id, state=state)
    account.sharekhan_login_state = state
    await add_audit_log(
        db,
        action="broker_account.login_state_update",
        entity_type="broker_account",
        entity_id=account_id,
        user_id=current_user.id,
    )
    await db.commit()
    return {**result, "state": state}


@router.get("/{account_id}/sharekhan/profile")
async def sharekhan_profile(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    account = await load_account(db, account_id, current_user)
    result = stored_sharekhan_profile_response(account)
    await add_audit_log(
        db,
        action="broker_account.profile_view",
        entity_type="broker_account",
        entity_id=account_id,
        user_id=current_user.id,
    )
    await db.commit()
    return result


@router.post("/{account_id}/sharekhan/token")
async def sharekhan_token(
    account_id: uuid.UUID,
    payload: SharekhanTokenExchange,
    background_tasks: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    result = await BrokerRouterClient().exchange_token(account_id, payload.request_token)
    await add_audit_log(
        db,
        action="broker_account.token_update",
        entity_type="broker_account",
        entity_id=account_id,
        user_id=current_user.id,
    )
    await db.commit()
    preload_exchanges = scheduled_login_preload_exchanges(result) if result.get("ok", True) else []
    if preload_exchanges:
        background_tasks.add_task(warm_script_master_after_login, account_id, result)
    result["script_master_preload"] = {
        "scheduled": bool(preload_exchanges),
        "exchanges": preload_exchanges,
    }
    return result


@router.post("/{account_id}/sharekhan/orders/place")
async def sharekhan_place_order(
    account_id: uuid.UUID,
    payload: SharekhanOrderPayload,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().place_order(account_id, payload.model_dump(mode="json"))


@router.post("/{account_id}/sharekhan/orders/modify")
async def sharekhan_modify_order(
    account_id: uuid.UUID,
    payload: SharekhanOrderPayload,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().modify_order(account_id, payload.model_dump(mode="json"))


@router.post("/{account_id}/sharekhan/orders/cancel")
async def sharekhan_cancel_order(
    account_id: uuid.UUID,
    payload: SharekhanOrderPayload,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().cancel_order(account_id, payload.model_dump(mode="json"))


@router.get("/{account_id}/sharekhan/funds/{exchange}")
async def sharekhan_funds(
    account_id: uuid.UUID,
    exchange: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().funds(account_id, exchange.upper())


@router.get("/{account_id}/sharekhan/reports")
async def sharekhan_reports(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().reports(account_id)


@router.get("/{account_id}/sharekhan/trades")
async def sharekhan_trades(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().trades(account_id)


@router.get("/{account_id}/sharekhan/orders/{exchange}/{order_id}")
async def sharekhan_order_details(
    account_id: uuid.UUID,
    exchange: str,
    order_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().order_details(account_id, exchange.upper(), order_id)


@router.get("/{account_id}/sharekhan/orders/{exchange}/{order_id}/trades")
async def sharekhan_order_trades(
    account_id: uuid.UUID,
    exchange: str,
    order_id: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().order_trades(account_id, exchange.upper(), order_id)


@router.get("/{account_id}/sharekhan/holdings")
async def sharekhan_holdings(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().holdings(account_id)


@router.get("/{account_id}/sharekhan/master/{exchange}")
async def sharekhan_master(
    account_id: uuid.UUID,
    exchange: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().master(exchange.upper(), account_id)


@router.get("/{account_id}/sharekhan/historical/{exchange}/{scripcode}/{interval}")
async def sharekhan_historical(
    account_id: uuid.UUID,
    exchange: str,
    scripcode: str,
    interval: str,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().historical(exchange.upper(), scripcode, interval, account_id)


@router.post("/{account_id}/sharekhan/ws/connect")
async def sharekhan_ws_connect(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().ws_connect(account_id)


@router.get("/{account_id}/sharekhan/ws/status")
async def sharekhan_ws_status(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().ws_status(account_id)


@router.post("/{account_id}/sharekhan/ws/subscribe")
async def sharekhan_ws_subscribe(
    account_id: uuid.UUID,
    payload: SharekhanWsSubscription,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().ws_subscribe(account_id, payload.model_dump(mode="json"))


@router.post("/{account_id}/sharekhan/ws/unsubscribe")
async def sharekhan_ws_unsubscribe(
    account_id: uuid.UUID,
    payload: SharekhanWsSubscription,
    db: DbSession,
    current_user: CurrentUser,
) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().ws_unsubscribe(account_id, payload.model_dump(mode="json"))


@router.post("/{account_id}/sharekhan/ws/disconnect")
async def sharekhan_ws_disconnect(account_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> dict[str, object]:
    await load_account(db, account_id, current_user)
    return await BrokerRouterClient().ws_disconnect(account_id)
