import uuid
import logging
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.responses import JSONResponse
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.brokers.sharekhan.client import SharekhanApiError, SharekhanRawClient, normalize_order_response
from app.brokers.sharekhan.token import SharekhanTokenError, convert_request_token_for_access_token
from app.core.config import get_settings
from app.db import SharekhanAccount, get_db, load_account, store_tokens
from app.limiter import rate_limiter
from app.schemas import AccountRequest, BrokerResponse, SharekhanOrderPayload, TokenExchangeRequest, WsSubscription
from app.security import mask_secret
from app.websocket_manager import stream_manager

app = FastAPI(title="Broker Router", version="0.1.0", dependencies=[Depends(rate_limiter)])
SHAREKHAN_LOGIN_STATE = "12345"
logger = logging.getLogger(__name__)


@app.exception_handler(SharekhanApiError)
async def sharekhan_api_error_handler(_: object, exc: SharekhanApiError) -> JSONResponse:
    logger.warning("Sharekhan API error: status=%s detail=%s", exc.status_code, exc.detail)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": f"Sharekhan API error ({exc.status_code}): {exc.detail}"},
    )


@app.exception_handler(httpx.RequestError)
async def sharekhan_request_error_handler(_: object, exc: httpx.RequestError) -> JSONResponse:
    logger.warning("Sharekhan network error: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Sharekhan API request failed before a response was received"},
    )


@app.get("/health")
async def health() -> dict[str, object]:
    return {"status": "ok", "paper_trading_mode": get_settings().paper_trading_mode}


async def _load_or_404(db: AsyncSession, account_id: uuid.UUID) -> SharekhanAccount:
    try:
        return await load_account(db, account_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


def _client(account: SharekhanAccount) -> SharekhanRawClient:
    settings = get_settings()
    return SharekhanRawClient(
        api_key=account.api_key,
        access_token=account.access_token,
        customer_id=account.customer_id,
        login_id=account.login_id,
        vendor_key=account.vendor_key,
        proxy_url=_proxy_url(account),
        base_url=settings.sharekhan_base_url,
        login_url=settings.sharekhan_login_url,
    )


def _proxy_url(account: SharekhanAccount) -> str | None:
    if not account.proxy_host or not account.proxy_port:
        return None
    auth = ""
    if account.proxy_username:
        auth = quote(account.proxy_username, safe="")
        if account.proxy_password:
            auth += f":{quote(account.proxy_password, safe='')}"
        auth += "@"
    return f"{account.proxy_scheme or 'http'}://{auth}{account.proxy_host}:{account.proxy_port}"


def _paper_order_response(account_id: uuid.UUID, payload: dict[str, Any]) -> BrokerResponse:
    broker_order_id = payload.get("orderId") or f"PAPER-{uuid.uuid4().hex[:12].upper()}"
    response = {
        "orderId": broker_order_id,
        "status": "PAPER_ACCEPTED",
        "message": "Paper trading mode is enabled; no broker order was sent.",
        "accountId": str(account_id),
        "requestType": payload.get("requestType"),
        "receivedAt": datetime.now(timezone.utc).isoformat(),
    }
    return BrokerResponse(
        ok=True,
        data=response,
        normalized=normalize_order_response(response),
        paper_trading=True,
    )


def _require_token(account: SharekhanAccount) -> None:
    if not account.access_token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sharekhan access token is missing")


def _require_api_key(account: SharekhanAccount) -> str:
    if not account.api_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sharekhan API key is missing")
    return account.api_key


def _require_secure_key(account: SharekhanAccount) -> str:
    if not account.secret_key:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Sharekhan Secure Key is missing")
    return account.secret_key


def _require_customer_id(account: SharekhanAccount) -> str:
    if not account.customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sharekhan customer ID is missing; complete token exchange first",
        )
    return account.customer_id


@app.post("/sharekhan/login-url")
async def login_url(payload: AccountRequest, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    account = await _load_or_404(db, payload.account_id)
    _require_api_key(account)
    return {"login_url": _client(account).generate_login_url(state=payload.state or SHAREKHAN_LOGIN_STATE)}


async def _fetch_and_store_profile(account: SharekhanAccount, db: AsyncSession) -> dict[str, object]:
    settings = get_settings()
    _require_api_key(account)
    secure_key = _require_secure_key(account)
    version_id = settings.sharekhan_version_id.strip()
    if not version_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="SHAREKHAN_VERSION_ID is missing; set it from the Sharekhan/Postman environment before exchanging access tokens",
        )
    if not account.request_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Sharekhan request token is missing; complete account login first",
        )
    try:
        converted = convert_request_token_for_access_token(account.request_token, secure_key)
    except SharekhanTokenError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    response = await _client(account).exchange_access_token(
        final_request_token=converted.final_encrypted_token,
        state=account.sharekhan_login_state or SHAREKHAN_LOGIN_STATE,
        version_id=version_id,
    )
    data = response.get("data") if isinstance(response.get("data"), dict) else response
    access_token = data.get("token") or data.get("accessToken") or data.get("access_token")
    refresh_token = data.get("refreshToken") or data.get("refresh_token")
    expires_in = data.get("expiresIn") or data.get("expires_in")
    customer_id = str(data.get("customerId") or data.get("customer_id") or converted.customer_id or account.customer_id or "")
    login_id = str(data.get("loginId") or data.get("login_id") or account.login_id or customer_id or "")
    exchanges = data.get("exchanges") or []
    if isinstance(exchanges, str):
        exchanges = [exchanges]
    elif not isinstance(exchanges, list):
        exchanges = []
    expires_at = None
    if expires_in:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            expires_at = None
    if not access_token:
        logger.warning("Sharekhan access token response missing token for account_id=%s", account.id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Sharekhan access-token response did not contain an access token",
        )

    await store_tokens(
        db,
        account.id,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=expires_at,
        customer_id=customer_id,
        login_id=login_id,
    )
    return {
        "ok": bool(access_token),
        "account_id": str(account.id),
        "access_token": mask_secret(access_token),
        "refresh_token": mask_secret(refresh_token),
        "customer_id": customer_id or None,
        "login_id": login_id or None,
        "full_name": data.get("fullName") or data.get("full_name"),
        "broker": data.get("broker"),
        "exchanges": exchanges,
        "token_expires_at": expires_at.isoformat() if expires_at else None,
        "raw_status": response.get("status"),
        "raw_message": response.get("message"),
    }


@app.post("/sharekhan/token/exchange")
async def exchange_token(payload: TokenExchangeRequest, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    account = await _load_or_404(db, payload.account_id)
    account = replace(account, request_token=payload.request_token)
    return await _fetch_and_store_profile(account, db)


@app.get("/sharekhan/accounts/{account_id}/profile")
async def account_profile(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    account = await _load_or_404(db, account_id)
    return await _fetch_and_store_profile(account, db)


@app.post("/sharekhan/accounts/{account_id}/orders/place", response_model=BrokerResponse)
async def place_order(
    account_id: uuid.UUID,
    payload: SharekhanOrderPayload,
    db: AsyncSession = Depends(get_db),
) -> BrokerResponse:
    account = await _load_or_404(db, account_id)
    if payload.requestType != "NEW":
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="place endpoint requires NEW requestType")
    body = payload.model_dump(mode="json")
    if get_settings().paper_trading_mode:
        return _paper_order_response(account_id, body | {"requestType": "NEW"})
    _require_token(account)
    response = await _client(account).place_order(body)
    return BrokerResponse(ok=True, data=response, normalized=normalize_order_response(response))


@app.post("/sharekhan/accounts/{account_id}/orders/modify", response_model=BrokerResponse)
async def modify_order(
    account_id: uuid.UUID,
    payload: SharekhanOrderPayload,
    db: AsyncSession = Depends(get_db),
) -> BrokerResponse:
    account = await _load_or_404(db, account_id)
    if not payload.orderId:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="orderId is required for modify")
    body = payload.model_dump(mode="json")
    if get_settings().paper_trading_mode:
        return _paper_order_response(account_id, body | {"requestType": "MODIFY"})
    _require_token(account)
    response = await _client(account).modify_order(body)
    return BrokerResponse(ok=True, data=response, normalized=normalize_order_response(response))


@app.post("/sharekhan/accounts/{account_id}/orders/cancel", response_model=BrokerResponse)
async def cancel_order(
    account_id: uuid.UUID,
    payload: SharekhanOrderPayload,
    db: AsyncSession = Depends(get_db),
) -> BrokerResponse:
    account = await _load_or_404(db, account_id)
    if not payload.orderId:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="orderId is required for cancel")
    body = payload.model_dump(mode="json")
    if get_settings().paper_trading_mode:
        return _paper_order_response(account_id, body | {"requestType": "CANCEL"})
    _require_token(account)
    response = await _client(account).cancel_order(body)
    return BrokerResponse(ok=True, data=response, normalized=normalize_order_response(response))


@app.get("/sharekhan/accounts/{account_id}/funds/{exchange}")
async def funds(account_id: uuid.UUID, exchange: str, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_token(account)
    return await _client(account).funds(exchange, _require_customer_id(account))


@app.get("/sharekhan/accounts/{account_id}/reports")
async def reports(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_token(account)
    return await _client(account).reports(_require_customer_id(account))


@app.get("/sharekhan/accounts/{account_id}/trades")
async def trades(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_token(account)
    return await _client(account).trades(_require_customer_id(account))


@app.get("/sharekhan/accounts/{account_id}/orders/{exchange}/{order_id}")
async def order_details(
    account_id: uuid.UUID,
    exchange: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_token(account)
    return await _client(account).order_details(exchange, _require_customer_id(account), order_id)


@app.get("/sharekhan/accounts/{account_id}/orders/{exchange}/{order_id}/trades")
async def order_trades(
    account_id: uuid.UUID,
    exchange: str,
    order_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_token(account)
    return await _client(account).order_trades(exchange, _require_customer_id(account), order_id)


@app.get("/sharekhan/accounts/{account_id}/holdings")
async def holdings(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_token(account)
    return await _client(account).holdings(_require_customer_id(account))


@app.get("/sharekhan/master/{exchange}")
async def master(exchange: str, account_id: uuid.UUID | None = Query(default=None), db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    if account_id:
        account = await _load_or_404(db, account_id)
        _require_token(account)
        return await _client(account).master(exchange)
    settings = get_settings()
    client = SharekhanRawClient(api_key="", base_url=settings.sharekhan_base_url, login_url=settings.sharekhan_login_url)
    return await client.master(exchange)


@app.get("/sharekhan/historical/{exchange}/{scripcode}/{interval}")
async def historical(
    exchange: str,
    scripcode: str,
    interval: str,
    account_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if account_id:
        account = await _load_or_404(db, account_id)
        _require_token(account)
        return await _client(account).historical(exchange, scripcode, interval)
    settings = get_settings()
    client = SharekhanRawClient(api_key="", base_url=settings.sharekhan_base_url, login_url=settings.sharekhan_login_url)
    return await client.historical(exchange, scripcode, interval)


@app.post("/sharekhan/ws/connect/{account_id}")
async def ws_connect(account_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    account = await _load_or_404(db, account_id)
    _require_api_key(account)
    _require_token(account)
    customer_id = account.customer_id
    return await stream_manager.connect(
        account_id,
        access_token=account.access_token or "",
        api_key=account.api_key,
        customer_id=customer_id,
        proxy_url=_proxy_url(account),
    )


@app.post("/sharekhan/ws/subscribe/{account_id}")
async def ws_subscribe(account_id: uuid.UUID, payload: WsSubscription) -> dict[str, Any]:
    return await stream_manager.subscribe(account_id, payload.symbols, payload.exchange)


@app.get("/sharekhan/ws/status/{account_id}")
async def ws_status(account_id: uuid.UUID) -> dict[str, Any]:
    return stream_manager.status(account_id)


@app.post("/sharekhan/ws/unsubscribe/{account_id}")
async def ws_unsubscribe(account_id: uuid.UUID, payload: WsSubscription) -> dict[str, Any]:
    return await stream_manager.unsubscribe(account_id, payload.symbols, payload.exchange)


@app.post("/sharekhan/ws/disconnect/{account_id}")
async def ws_disconnect(account_id: uuid.UUID) -> dict[str, Any]:
    return await stream_manager.disconnect(account_id)
