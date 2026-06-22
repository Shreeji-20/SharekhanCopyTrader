from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

from app.models import BrokerAccount, ScriptMasterInstrument, UserRole
from app.routers.script_master import (
    _account_for_user,
    _watchlist_read,
    add_script_master_watchlist_item,
    search_script_master,
)
from app.schemas import ScriptMasterWatchlistCreate


class FakeDb:
    def __init__(self, account: object | None = None, instrument: object | None = None, existing_item: object | None = None) -> None:
        self.account = account
        self.instrument = instrument
        self.existing_item = existing_item
        self.added: list[object] = []
        self.committed = False
        self.get_calls = 0
        self.scalar_calls = 0
        self.scalars_calls = 0

    async def get(self, model: type[object], item_id: uuid.UUID) -> object | None:
        self.get_calls += 1
        if model is BrokerAccount and self.account and getattr(self.account, "id") == item_id:
            return self.account
        if model is ScriptMasterInstrument and self.instrument and getattr(self.instrument, "id") == item_id:
            return self.instrument
        return None

    async def scalar(self, statement: object) -> object | None:
        self.scalar_calls += 1
        return self.existing_item

    async def scalars(self, statement: object) -> object:
        self.scalars_calls += 1
        return SimpleNamespace(all=lambda: [])

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def refresh(self, item: object) -> None:
        return None


def user(user_id: uuid.UUID) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=UserRole.USER)


def instrument(**overrides: object) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    data = {
        "id": uuid.uuid4(),
        "exchange": "NC",
        "segment": "EQ",
        "scrip_code": "2475",
        "trading_symbol": "IDEA",
        "symbol_name": "VODAFONE IDEA",
        "underlying_symbol": "IDEA",
        "instrument_type": "EQ",
        "option_type": None,
        "strike_price": None,
        "expiry_date": None,
        "lot_size": 1,
        "tick_size": Decimal("0.0500"),
        "isin": "INE669E01016",
        "raw_payload_json": {"tradingSymbol": "IDEA"},
        "refreshed_at": now,
        "created_at": now,
        "updated_at": now,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def watchlist_item(account_id: uuid.UUID, user_id: uuid.UUID, source: SimpleNamespace | None = None) -> SimpleNamespace:
    source = source or instrument()
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        account_id=account_id,
        exchange=source.exchange,
        scrip_code=source.scrip_code,
        instrument_snapshot_json={
            "id": str(source.id),
            "exchange": source.exchange,
            "segment": source.segment,
            "scrip_code": source.scrip_code,
            "trading_symbol": source.trading_symbol,
            "symbol_name": source.symbol_name,
            "underlying_symbol": source.underlying_symbol,
            "instrument_type": source.instrument_type,
            "option_type": source.option_type,
            "strike_price": source.strike_price,
            "expiry_date": source.expiry_date,
            "lot_size": source.lot_size,
            "tick_size": str(source.tick_size),
            "isin": source.isin,
            "raw_payload_json": source.raw_payload_json,
            "refreshed_at": source.refreshed_at,
            "created_at": source.created_at,
            "updated_at": source.updated_at,
        },
        created_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_watchlist_rejects_account_owned_by_another_user() -> None:
    current_user_id = uuid.uuid4()
    account = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())
    db = FakeDb(account=account)

    with pytest.raises(HTTPException) as exc:
        await _account_for_user(db, account.id, user(current_user_id))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_watchlist_add_returns_existing_duplicate_without_insert() -> None:
    current_user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    script = instrument()
    existing = watchlist_item(account_id, current_user_id, script)
    db = FakeDb(
        account=SimpleNamespace(id=account_id, user_id=current_user_id),
        instrument=script,
        existing_item=existing,
    )

    result = await add_script_master_watchlist_item(
        ScriptMasterWatchlistCreate(account_id=account_id, instrument_id=script.id),
        db,
        user(current_user_id),
    )

    assert result.id == existing.id
    assert result.instrument.trading_symbol == "IDEA"
    assert db.added == []
    assert db.committed is False


def test_watchlist_read_falls_back_to_saved_snapshot_when_cache_row_is_missing() -> None:
    account_id = uuid.uuid4()
    source = instrument()
    item = watchlist_item(account_id, uuid.uuid4(), source)

    result = _watchlist_read(item, None)

    assert result.account_id == account_id
    assert result.instrument.id is None
    assert result.instrument.trading_symbol == "IDEA"
    assert result.instrument.tick_size == Decimal("0.0500")


@pytest.mark.asyncio
async def test_search_ignores_one_character_queries() -> None:
    db = FakeDb()

    result = await search_script_master(db, user(uuid.uuid4()), query="i")

    assert result == []
    assert db.scalars_calls == 0
