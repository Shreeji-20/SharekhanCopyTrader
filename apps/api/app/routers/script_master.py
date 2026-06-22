import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, or_, select

from app.audit import add_audit_log
from app.dependencies import CurrentUser, DbSession
from app.models import BrokerAccount, ScriptMasterInstrument, ScriptMasterWatchlistItem, UserRole
from app.schemas import (
    ScriptMasterInstrumentRead,
    ScriptMasterSearchResult,
    ScriptMasterWatchlistCreate,
    ScriptMasterWatchlistRead,
)
from app.services.script_master import script_master_service

router = APIRouter(prefix="/script-master", tags=["script-master"])


async def _account_for_user(db: DbSession, account_id: uuid.UUID, current_user: CurrentUser) -> BrokerAccount:
    account = await db.get(BrokerAccount, account_id)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if current_user.role != UserRole.ADMIN and account.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not allowed")
    return account


def _json_value(value: Any) -> Any:
    if isinstance(value, (uuid.UUID, datetime, date, Decimal)):
        return str(value)
    return value


def _instrument_payload(instrument: ScriptMasterInstrument) -> dict[str, Any]:
    return {
        "id": instrument.id,
        "exchange": instrument.exchange,
        "segment": instrument.segment,
        "scrip_code": instrument.scrip_code,
        "trading_symbol": instrument.trading_symbol,
        "symbol_name": instrument.symbol_name,
        "underlying_symbol": instrument.underlying_symbol,
        "instrument_type": instrument.instrument_type,
        "option_type": instrument.option_type,
        "strike_price": instrument.strike_price,
        "expiry_date": instrument.expiry_date,
        "lot_size": instrument.lot_size,
        "tick_size": instrument.tick_size,
        "isin": instrument.isin,
        "raw_payload_json": instrument.raw_payload_json,
        "refreshed_at": instrument.refreshed_at,
        "created_at": instrument.created_at,
        "updated_at": instrument.updated_at,
    }


def _instrument_snapshot(instrument: ScriptMasterInstrument) -> dict[str, Any]:
    return {key: _json_value(value) for key, value in _instrument_payload(instrument).items()}


def _snapshot_read(snapshot: dict[str, Any]) -> ScriptMasterInstrumentRead:
    payload = dict(snapshot)
    payload["id"] = None
    payload.setdefault("raw_payload_json", {})
    return ScriptMasterInstrumentRead.model_validate(payload)


def _instrument_read(instrument: ScriptMasterInstrument) -> ScriptMasterInstrumentRead:
    return ScriptMasterInstrumentRead.model_validate(instrument)


def _watchlist_read(
    item: ScriptMasterWatchlistItem,
    instrument: ScriptMasterInstrument | None,
) -> ScriptMasterWatchlistRead:
    return ScriptMasterWatchlistRead(
        id=item.id,
        account_id=item.account_id,
        instrument=_instrument_read(instrument) if instrument else _snapshot_read(item.instrument_snapshot_json),
        created_at=item.created_at,
    )


async def _watchlist_item_for_user(
    db: DbSession,
    item_id: uuid.UUID,
    current_user: CurrentUser,
) -> ScriptMasterWatchlistItem:
    item = await db.get(ScriptMasterWatchlistItem, item_id)
    if not item or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist item not found")
    return item


@router.get("/search", response_model=list[ScriptMasterSearchResult])
async def search_script_master(
    db: DbSession,
    current_user: CurrentUser,
    query: str = Query(..., min_length=1),
    account_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ScriptMasterSearchResult]:
    search_text = query.strip()
    if len(search_text) < 2:
        return []
    if account_id:
        await _account_for_user(db, account_id, current_user)

    pattern = f"%{search_text}%"
    statement = (
        select(ScriptMasterInstrument)
        .where(
            or_(
                ScriptMasterInstrument.trading_symbol.ilike(pattern),
                ScriptMasterInstrument.symbol_name.ilike(pattern),
                ScriptMasterInstrument.underlying_symbol.ilike(pattern),
                ScriptMasterInstrument.scrip_code.ilike(pattern),
                ScriptMasterInstrument.isin.ilike(pattern),
            )
        )
        .order_by(
            ScriptMasterInstrument.trading_symbol.asc(),
            ScriptMasterInstrument.exchange.asc(),
            ScriptMasterInstrument.expiry_date.asc().nullsfirst(),
            ScriptMasterInstrument.strike_price.asc().nullsfirst(),
        )
        .limit(limit)
    )
    instruments = list((await db.scalars(statement)).all())

    watchlist_by_key: dict[tuple[str, str], uuid.UUID] = {}
    if account_id and instruments:
        rows = (
            await db.scalars(
                select(ScriptMasterWatchlistItem).where(
                    ScriptMasterWatchlistItem.user_id == current_user.id,
                    ScriptMasterWatchlistItem.account_id == account_id,
                    ScriptMasterWatchlistItem.exchange.in_([instrument.exchange for instrument in instruments]),
                    ScriptMasterWatchlistItem.scrip_code.in_([instrument.scrip_code for instrument in instruments]),
                )
            )
        ).all()
        watchlist_by_key = {(row.exchange, row.scrip_code): row.id for row in rows}

    return [
        ScriptMasterSearchResult(
            **_instrument_read(instrument).model_dump(),
            is_watchlisted=(instrument.exchange, instrument.scrip_code) in watchlist_by_key,
            watchlist_id=watchlist_by_key.get((instrument.exchange, instrument.scrip_code)),
        )
        for instrument in instruments
    ]


@router.post("/watchlist", response_model=ScriptMasterWatchlistRead, status_code=status.HTTP_201_CREATED)
async def add_script_master_watchlist_item(
    payload: ScriptMasterWatchlistCreate,
    db: DbSession,
    current_user: CurrentUser,
) -> ScriptMasterWatchlistRead:
    account = await _account_for_user(db, payload.account_id, current_user)
    instrument = await db.get(ScriptMasterInstrument, payload.instrument_id)
    if not instrument:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script Master instrument not found")

    existing = await db.scalar(
        select(ScriptMasterWatchlistItem).where(
            ScriptMasterWatchlistItem.user_id == current_user.id,
            ScriptMasterWatchlistItem.account_id == account.id,
            ScriptMasterWatchlistItem.exchange == instrument.exchange,
            ScriptMasterWatchlistItem.scrip_code == instrument.scrip_code,
        )
    )
    if existing:
        return _watchlist_read(existing, instrument)

    item = ScriptMasterWatchlistItem(
        user_id=current_user.id,
        account_id=account.id,
        exchange=instrument.exchange,
        scrip_code=instrument.scrip_code,
        instrument_snapshot_json=_instrument_snapshot(instrument),
    )
    db.add(item)
    await db.flush()
    await add_audit_log(
        db,
        action="script_master.watchlist_add",
        entity_type="script_master_watchlist",
        entity_id=item.id,
        user_id=current_user.id,
        metadata={"account_id": str(account.id), "exchange": instrument.exchange, "scrip_code": instrument.scrip_code},
    )
    await db.commit()
    await db.refresh(item)
    return _watchlist_read(item, instrument)


@router.get("/watchlist", response_model=list[ScriptMasterWatchlistRead])
async def list_script_master_watchlist(
    db: DbSession,
    current_user: CurrentUser,
    account_id: uuid.UUID | None = Query(default=None),
) -> list[ScriptMasterWatchlistRead]:
    if account_id:
        await _account_for_user(db, account_id, current_user)
    statement = (
        select(ScriptMasterWatchlistItem, ScriptMasterInstrument)
        .outerjoin(
            ScriptMasterInstrument,
            and_(
                ScriptMasterInstrument.exchange == ScriptMasterWatchlistItem.exchange,
                ScriptMasterInstrument.scrip_code == ScriptMasterWatchlistItem.scrip_code,
            ),
        )
        .where(ScriptMasterWatchlistItem.user_id == current_user.id)
        .order_by(ScriptMasterWatchlistItem.created_at.desc())
    )
    if account_id:
        statement = statement.where(ScriptMasterWatchlistItem.account_id == account_id)
    rows = (await db.execute(statement)).all()
    return [_watchlist_read(item, instrument) for item, instrument in rows]


@router.delete("/watchlist/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_script_master_watchlist_item(
    item_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
) -> None:
    item = await _watchlist_item_for_user(db, item_id, current_user)
    await db.delete(item)
    await add_audit_log(
        db,
        action="script_master.watchlist_remove",
        entity_type="script_master_watchlist",
        entity_id=item_id,
        user_id=current_user.id,
        metadata={"account_id": str(item.account_id), "exchange": item.exchange, "scrip_code": item.scrip_code},
    )
    await db.commit()


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
