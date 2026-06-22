import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal
from time import perf_counter
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException

from app.models import CopiedTradeOrderStatus, CopySessionStatus, PriceMode, SizingMode
from app.schemas import CopySessionRead
from app.services.live_copy import (
    CopyRiskUsage,
    CopySkip,
    CopyTargetPlan,
    NormalizedTradeEvent,
    build_sharekhan_copy_order_payload,
    live_copy_manager,
    normalize_sharekhan_ack,
)
from app.services.script_master import (
    AMBIGUOUS,
    CACHE_EMPTY,
    RESOLVED,
    UNRESOLVED,
    ScriptMasterResolution,
    ScriptMasterLookup,
    ScriptMasterService,
    match_script_master_records,
    normalize_script_master_response,
)


def script_record(
    *,
    scrip_code: str = "2475",
    trading_symbol: str = "ONGC",
    exchange: str = "NC",
    segment: str | None = None,
    instrument_type: str | None = "EQ",
    option_type: str | None = None,
    strike_price: Decimal | None = None,
    expiry_date: date | None = None,
    lot_size: int | None = None,
    tick_size: Decimal | None = None,
    isin: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        exchange=exchange,
        segment=segment,
        scrip_code=scrip_code,
        trading_symbol=trading_symbol,
        symbol_name=None,
        underlying_symbol=None,
        instrument_type=instrument_type,
        option_type=option_type,
        strike_price=strike_price,
        expiry_date=expiry_date,
        lot_size=lot_size,
        tick_size=tick_size,
        isin=isin,
    )


def copy_event(**overrides: object) -> NormalizedTradeEvent:
    data = {
        "external_trade_id": "T1",
        "external_order_id": "O1",
        "symbol": "ONGC",
        "exchange": "NC",
        "side": "B",
        "quantity": 2,
        "price": Decimal("93.10"),
        "order_type": "NORMAL",
        "product_type": "INVESTMENT",
        "raw_payload": {},
        "event_time": None,
        "duplicate_hash": "hash",
        "scrip_code": 2475,
    }
    data.update(overrides)
    return NormalizedTradeEvent(**data)


def copy_setting(**overrides: object) -> SimpleNamespace:
    data = {
        "sizing_mode": SizingMode.SAME_QTY,
        "multiplier": Decimal("1"),
        "fixed_qty": None,
        "capital_percent": None,
        "min_qty": None,
        "max_qty": None,
        "max_trades_per_day": None,
        "max_daily_loss": None,
        "max_order_value": None,
        "allowed_symbols": [],
        "blocked_symbols": [],
        "allowed_transaction_types": ["B", "S"],
        "allowed_product_types": [],
        "product_type_map": {},
        "price_mode": PriceMode.SAME_PRICE,
        "max_slippage_percent": None,
        "is_auto_squareoff_enabled": False,
        "is_enabled": True,
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def copy_account(**overrides: object) -> SimpleNamespace:
    data = {
        "id": uuid.uuid4(),
        "account_name": "Copy Account",
        "is_active": True,
        "api_key": "encrypted-api-key",
        "secret_key": "encrypted-secret-key",
        "customer_id": "CUSTOMER1",
        "login_id": "LOGIN1",
        "access_token": "encrypted-access-token",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_normalize_sharekhan_ack_extracts_order_confirmation_without_trade_qty() -> None:
    payload = {
        "status": 100,
        "message": "feed",
        "data": {
            "SharekhanOrderID": "245749050",
            "AckState": "NewOrderConfirmation",
            "TradingSymbol": "ONGC",
            "BuySellString": "B",
            "OrderQty": 1,
            "TradeQty": 0,
            "OrderPrice": "92.50",
            "Exchange": "NC",
        },
    }

    event = normalize_sharekhan_ack(payload)

    assert event is not None
    assert event.external_trade_id is None
    assert event.external_order_id == "245749050"
    assert event.symbol == "ONGC"
    assert event.exchange == "NC"
    assert event.side == "B"
    assert event.quantity == 1
    assert event.price == Decimal("92.50")


def test_normalize_sharekhan_ack_extracts_executed_trade() -> None:
    payload = {
        "status": 100,
        "message": "feed",
        "timestamp": "2021-03-02T11:30:01+05:30",
        "data": {
            "SharekhanOrderID": "245749050",
            "ExchangeOrderID": "1000000000000678",
            "AckState": "TradeConfirmation",
            "TradingSymbol": "ONGC",
            "BuySellString": "B",
            "OrderQty": 5,
            "TradeQty": 2,
            "OrderPrice": "92.50",
            "TradePrice": "93.10",
            "TradeID": "8765",
            "ExchangeDateTime": "02/03/2021 12:02:08",
            "Exchange": "NC",
            "ScripCode": 2475,
            "OrderType": "NOR",
        },
    }

    event = normalize_sharekhan_ack(payload)

    assert event is not None
    assert event.external_trade_id == "8765"
    assert event.external_order_id == "245749050"
    assert event.symbol == "ONGC"
    assert event.exchange == "NC"
    assert event.side == "B"
    assert event.quantity == 2
    assert event.price == Decimal("93.10")
    assert event.order_type == "NORMAL"
    assert event.scrip_code == 2475


def test_normalize_sharekhan_ack_dedupes_fill_after_order_confirmation() -> None:
    order_confirmation = {
        "status": 100,
        "message": "feed",
        "data": {
            "SharekhanOrderID": "245749050",
            "AckState": "NewOrderConfirmation",
            "TradingSymbol": "ONGC",
            "BuySellString": "BUY",
            "OrderQty": 5,
            "TradeQty": 0,
            "OrderPrice": "92.50",
            "Exchange": "NC",
            "ScripCode": 2475,
        },
    }
    trade_confirmation = {
        "status": 100,
        "message": "feed",
        "data": {
            "SharekhanOrderID": "245749050",
            "AckState": "TradeConfirmation",
            "TradingSymbol": "ONGC",
            "BuySellString": "B",
            "OrderQty": 5,
            "TradeQty": 2,
            "TradePrice": "93.10",
            "TradeID": "8765",
            "Exchange": "NC",
            "ScripCode": 2475,
        },
    }

    order_event = normalize_sharekhan_ack(order_confirmation)
    trade_event = normalize_sharekhan_ack(trade_confirmation)

    assert order_event is not None
    assert trade_event is not None
    assert order_event.side == "B"
    assert order_event.duplicate_hash == trade_event.duplicate_hash


def test_normalize_sharekhan_ack_handles_lower_camel_case() -> None:
    payload = {
        "status": 100,
        "message": "feed",
        "data": {
            "sharekhanOrderId": "245749050",
            "ackState": "TradeConfirmation",
            "tradingSymbol": "ONGC",
            "buySellString": "S",
            "orderQty": 5,
            "tradeQty": 1,
            "tradePrice": "91.10",
            "tradeId": "8766",
            "exchange": "NC",
            "scripCode": 2475,
        },
    }

    event = normalize_sharekhan_ack(payload)

    assert event is not None
    assert event.external_trade_id == "8766"
    assert event.side == "S"
    assert event.quantity == 1
    assert event.scrip_code == 2475


def test_build_sharekhan_copy_order_payload_uses_settings_and_account_identity() -> None:
    event = NormalizedTradeEvent(
        external_trade_id="T1",
        external_order_id="O1",
        symbol="ONGC",
        exchange="NC",
        side="B",
        quantity=2,
        price=Decimal("93.10"),
        order_type="NORMAL",
        product_type="INVESTMENT",
        raw_payload={},
        event_time=None,
        duplicate_hash="hash",
        scrip_code=2475,
    )
    setting = SimpleNamespace(
        sizing_mode=SizingMode.MULTIPLIER,
        multiplier=Decimal("1.5"),
        fixed_qty=None,
        max_qty=10,
        max_order_value=Decimal("1000"),
        allowed_symbols=["ONGC"],
        blocked_symbols=[],
        allowed_transaction_types=["B"],
        allowed_product_types=["INVESTMENT"],
        product_type_map={},
        price_mode=PriceMode.SAME_PRICE,
        max_slippage_percent=None,
        is_enabled=True,
    )
    account = SimpleNamespace(
        is_active=True,
        api_key="encrypted-api-key",
        secret_key="encrypted-secret-key",
        customer_id="CUSTOMER1",
        login_id="LOGIN1",
        access_token="encrypted-access-token",
    )

    payload = build_sharekhan_copy_order_payload(event, setting, account)

    assert payload["customerId"] == "CUSTOMER1"
    assert payload["channelUser"] == "LOGIN1"
    assert payload["scripCode"] == 2475
    assert payload["tradingSymbol"] == "ONGC"
    assert payload["transactionType"] == "B"
    assert payload["quantity"] == 3
    assert payload["price"] == "93.10"
    assert payload["requestType"] == "NEW"


def test_build_sharekhan_copy_order_payload_requires_scrip_code() -> None:
    event = NormalizedTradeEvent(
        external_trade_id="T1",
        external_order_id="O1",
        symbol="ONGC",
        exchange="NC",
        side="B",
        quantity=1,
        price=Decimal("93.10"),
        order_type="NORMAL",
        product_type="INVESTMENT",
        raw_payload={},
        event_time=None,
        duplicate_hash="hash",
    )
    setting = SimpleNamespace(
        sizing_mode=SizingMode.SAME_QTY,
        multiplier=Decimal("1"),
        fixed_qty=None,
        max_qty=None,
        max_order_value=None,
        allowed_symbols=[],
        blocked_symbols=[],
        allowed_transaction_types=["B", "S"],
        allowed_product_types=[],
        product_type_map={},
        price_mode=PriceMode.SAME_PRICE,
        max_slippage_percent=None,
        is_enabled=True,
    )
    account = SimpleNamespace(
        is_active=True,
        api_key="encrypted-api-key",
        secret_key="encrypted-secret-key",
        customer_id="CUSTOMER1",
        login_id="LOGIN1",
        access_token="encrypted-access-token",
    )

    with pytest.raises(CopySkip, match="scripCode"):
        build_sharekhan_copy_order_payload(event, setting, account)


def test_fixed_quantity_setting_is_applied_per_membership() -> None:
    account = copy_account()

    first_payload = build_sharekhan_copy_order_payload(
        copy_event(),
        copy_setting(sizing_mode=SizingMode.FIXED_QTY, fixed_qty=1),
        account,
    )
    second_payload = build_sharekhan_copy_order_payload(
        copy_event(),
        copy_setting(sizing_mode=SizingMode.FIXED_QTY, fixed_qty=5),
        account,
    )

    assert first_payload["quantity"] == 1
    assert second_payload["quantity"] == 5


def test_copy_payload_skips_when_quantity_is_below_min_qty() -> None:
    with pytest.raises(CopySkip, match="below min_qty"):
        build_sharekhan_copy_order_payload(copy_event(quantity=2), copy_setting(min_qty=3), copy_account())


def test_copy_payload_skips_when_quantity_exceeds_max_qty() -> None:
    with pytest.raises(CopySkip, match="exceeds max_qty"):
        build_sharekhan_copy_order_payload(copy_event(quantity=5), copy_setting(max_qty=3), copy_account())


def test_copy_payload_skips_when_order_value_exceeds_limit() -> None:
    with pytest.raises(CopySkip, match="max_order_value"):
        build_sharekhan_copy_order_payload(copy_event(quantity=5), copy_setting(max_order_value=Decimal("100")), copy_account())


def test_copy_payload_skips_when_daily_trade_limit_reached() -> None:
    with pytest.raises(CopySkip, match="max_trades_per_day"):
        build_sharekhan_copy_order_payload(
            copy_event(),
            copy_setting(max_trades_per_day=2),
            copy_account(),
            CopyRiskUsage(trades_today=2),
        )


def test_copy_payload_skips_when_daily_loss_limit_reached() -> None:
    with pytest.raises(CopySkip, match="max_daily_loss"):
        build_sharekhan_copy_order_payload(
            copy_event(),
            copy_setting(max_daily_loss=Decimal("500")),
            copy_account(),
            CopyRiskUsage(current_daily_loss=Decimal("500")),
        )


@pytest.mark.asyncio
async def test_copy_targets_are_dispatched_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(id=uuid.uuid4(), dry_run=False)
    targets = tuple(
        CopyTargetPlan(
            member_id=uuid.uuid4(),
            copy_group_id=uuid.uuid4(),
            copy_group_name=f"Group {index}",
            setting=copy_setting(),
            copy_account=copy_account(account_name=f"Copy {index}"),
        )
        for index in range(5)
    )

    monkeypatch.setattr(
        "app.services.live_copy.get_settings",
        lambda: SimpleNamespace(
            broker_router_url="http://broker-router",
            paper_trading_mode=False,
            copy_trading_dry_run=False,
            live_copy_order_dispatch_concurrency=0,
        ),
    )

    async def fake_place_order(self: object, account_id: uuid.UUID, payload: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0.05)
        return {"orderId": str(account_id), "ok": True}

    monkeypatch.setattr("app.services.live_copy.BrokerRouterClient.place_order", fake_place_order)

    started = perf_counter()
    results = await live_copy_manager._copy_targets_concurrently(session, copy_event(), targets, {})
    elapsed = perf_counter() - started

    assert len(results) == 5
    assert {result.order_status for result in results} == {CopiedTradeOrderStatus.PLACED}
    assert max(result.dispatch_gap_ms or 0 for result in results) < 25
    assert elapsed < 0.18


@pytest.mark.asyncio
async def test_failed_copier_result_does_not_block_other_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(id=uuid.uuid4(), dry_run=False)
    failing_account_id = uuid.uuid4()
    targets = (
        CopyTargetPlan(uuid.uuid4(), uuid.uuid4(), "Group A", copy_setting(), copy_account(id=failing_account_id)),
        CopyTargetPlan(uuid.uuid4(), uuid.uuid4(), "Group B", copy_setting(), copy_account()),
    )

    monkeypatch.setattr(
        "app.services.live_copy.get_settings",
        lambda: SimpleNamespace(
            broker_router_url="http://broker-router",
            paper_trading_mode=False,
            copy_trading_dry_run=False,
            live_copy_order_dispatch_concurrency=0,
        ),
    )

    async def fake_place_order(self: object, account_id: uuid.UUID, payload: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0.02)
        if account_id == failing_account_id:
            raise HTTPException(status_code=403, detail="token expired")
        return {"orderId": "ORDER2", "ok": True}

    monkeypatch.setattr("app.services.live_copy.BrokerRouterClient.place_order", fake_place_order)

    results = await live_copy_manager._copy_targets_concurrently(session, copy_event(), targets, {})

    assert [result.order_status for result in results] == [CopiedTradeOrderStatus.FAILED, CopiedTradeOrderStatus.PLACED]
    assert results[0].error_message == "token expired"


@pytest.mark.asyncio
async def test_missing_token_in_one_copier_does_not_block_valid_copier(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(id=uuid.uuid4(), dry_run=False)
    targets = (
        CopyTargetPlan(uuid.uuid4(), uuid.uuid4(), "Group A", copy_setting(), copy_account(access_token=None)),
        CopyTargetPlan(uuid.uuid4(), uuid.uuid4(), "Group B", copy_setting(), copy_account()),
    )
    monkeypatch.setattr(
        "app.services.live_copy.get_settings",
        lambda: SimpleNamespace(
            broker_router_url="http://broker-router",
            paper_trading_mode=False,
            copy_trading_dry_run=False,
            live_copy_order_dispatch_concurrency=0,
        ),
    )

    async def fake_place_order(self: object, account_id: uuid.UUID, payload: dict[str, object]) -> dict[str, object]:
        return {"orderId": "ORDER3", "ok": True}

    monkeypatch.setattr("app.services.live_copy.BrokerRouterClient.place_order", fake_place_order)

    results = await live_copy_manager._copy_targets_concurrently(session, copy_event(), targets, {})

    assert [result.order_status for result in results] == [CopiedTradeOrderStatus.SKIPPED, CopiedTradeOrderStatus.PLACED]
    assert "access_token" in (results[0].error_message or "")


@pytest.mark.asyncio
async def test_dispatch_concurrency_limit_is_respected(monkeypatch: pytest.MonkeyPatch) -> None:
    session = SimpleNamespace(id=uuid.uuid4(), dry_run=False)
    targets = tuple(
        CopyTargetPlan(uuid.uuid4(), uuid.uuid4(), f"Group {index}", copy_setting(), copy_account())
        for index in range(3)
    )
    monkeypatch.setattr(
        "app.services.live_copy.get_settings",
        lambda: SimpleNamespace(
            broker_router_url="http://broker-router",
            paper_trading_mode=False,
            copy_trading_dry_run=False,
            live_copy_order_dispatch_concurrency=1,
        ),
    )

    async def fake_place_order(self: object, account_id: uuid.UUID, payload: dict[str, object]) -> dict[str, object]:
        await asyncio.sleep(0.03)
        return {"orderId": str(account_id), "ok": True}

    monkeypatch.setattr("app.services.live_copy.BrokerRouterClient.place_order", fake_place_order)

    started = perf_counter()
    results = await live_copy_manager._copy_targets_concurrently(session, copy_event(), targets, {})
    elapsed = perf_counter() - started

    assert [result.order_status for result in results] == [CopiedTradeOrderStatus.PLACED] * 3
    assert elapsed >= 0.09


def test_script_master_equity_match_resolves_missing_scrip_code() -> None:
    resolution = match_script_master_records(
        [script_record(scrip_code="2475", trading_symbol="ONGC", exchange="NC", instrument_type="EQ")],
        ScriptMasterLookup(symbol="ONGC", exchange="NC"),
    )

    assert resolution.status == RESOLVED
    assert resolution.scrip_code == 2475
    assert "scripCode resolved from Script Master" in resolution.message


def test_script_master_derivative_ce_match_resolves_missing_scrip_code() -> None:
    resolution = match_script_master_records(
        [
            script_record(
                scrip_code="60530",
                trading_symbol="NIFTY",
                exchange="NF",
                instrument_type="FI",
                option_type="CE",
                strike_price=Decimal("23400.0000"),
                expiry_date=date(2026, 6, 9),
                lot_size=75,
            )
        ],
        ScriptMasterLookup(
            symbol="NIFTY",
            exchange="NF",
            instrument_type="FI",
            option_type="CE",
            strike_price=Decimal("23400"),
            expiry_date="09/06/2026",
            lot_size=75,
        ),
    )

    assert resolution.status == RESOLVED
    assert resolution.scrip_code == 60530


def test_script_master_derivative_pe_match_resolves_missing_scrip_code() -> None:
    resolution = match_script_master_records(
        [
            script_record(
                scrip_code="60531",
                trading_symbol="NIFTY",
                exchange="NF",
                instrument_type="OI",
                option_type="PE",
                strike_price=Decimal("23400.0000"),
                expiry_date=date(2026, 6, 9),
            )
        ],
        ScriptMasterLookup(
            symbol="NIFTY",
            exchange="NF",
            instrument_type="OI",
            option_type="PE",
            strike_price=Decimal("23400"),
            expiry_date=date(2026, 6, 9),
        ),
    )

    assert resolution.status == RESOLVED
    assert resolution.scrip_code == 60531


def test_script_master_unmatched_symbol_returns_clear_error() -> None:
    resolution = match_script_master_records(
        [script_record(scrip_code="2475", trading_symbol="ONGC", exchange="NC")],
        ScriptMasterLookup(symbol="RELIANCE", exchange="NC"),
    )

    assert resolution.status == UNRESOLVED
    assert "scripCode missing and could not be resolved" in resolution.message


def test_script_master_ambiguous_symbol_does_not_resolve_blindly() -> None:
    resolution = match_script_master_records(
        [
            script_record(scrip_code="111", trading_symbol="ABC", exchange="NC", instrument_type="EQ"),
            script_record(scrip_code="222", trading_symbol="ABC", exchange="NC", instrument_type="EQ"),
        ],
        ScriptMasterLookup(symbol="ABC", exchange="NC"),
    )

    assert resolution.status == AMBIGUOUS
    assert resolution.scrip_code is None
    assert "multiple Script Master matches found" in resolution.message


def test_script_master_empty_cache_returns_cache_empty_status() -> None:
    resolution = match_script_master_records([], ScriptMasterLookup(symbol="ONGC", exchange="NC"))

    assert resolution.status == CACHE_EMPTY
    assert "cache for NC is empty" in resolution.message


def test_script_master_normalizes_delimited_master_response() -> None:
    response = {
        "data": "scripCode|tradingSymbol|exchange|instrumentType|tickSize|isin\n2475|ONGC|NC|EQ|0.05|INE213A01029\n"
    }

    rows = normalize_script_master_response(response, "NC")

    assert len(rows) == 1
    assert rows[0].scrip_code == "2475"
    assert rows[0].trading_symbol == "ONGC"
    assert rows[0].tick_size == Decimal("0.0500")
    assert rows[0].isin == "INE213A01029"


class FakeScalarResult:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self._rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self._rows


class FakeScriptMasterDb:
    def __init__(self, rows: list[SimpleNamespace] | None = None) -> None:
        self.rows = rows or []
        self.scalars_calls = 0
        self.execute_calls = 0
        self.flush_calls = 0

    async def scalars(self, statement: object) -> FakeScalarResult:
        self.scalars_calls += 1
        return FakeScalarResult(self.rows)

    async def execute(self, statement: object, *args: object) -> None:
        self.execute_calls += 1

    async def flush(self) -> None:
        self.flush_calls += 1


class FakeBrokerRouter:
    def __init__(self, response: object, delay_seconds: float = 0) -> None:
        self.response = response
        self.delay_seconds = delay_seconds
        self.master_calls = 0

    async def master(self, exchange: str, account_id: uuid.UUID) -> object:
        self.master_calls += 1
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        return self.response


@pytest.mark.asyncio
async def test_script_master_resolve_reuses_in_memory_exchange_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime.now(timezone.utc)
    row = script_record(scrip_code="2475", trading_symbol="ONGC", exchange="NC", instrument_type="EQ")
    row.refreshed_at = now
    db = FakeScriptMasterDb([row])
    broker = FakeBrokerRouter({})
    service = ScriptMasterService(broker_router=broker)
    monkeypatch.setenv("SCRIPT_MASTER_CACHE_TTL_HOURS", "24")

    first = await service.resolve(db, ScriptMasterLookup(symbol="ONGC", exchange="NC"), uuid.uuid4())
    second = await service.resolve(db, ScriptMasterLookup(symbol="ONGC", exchange="NC"), uuid.uuid4())

    assert first.status == RESOLVED
    assert second.status == RESOLVED
    assert db.scalars_calls == 1
    assert broker.master_calls == 0


@pytest.mark.asyncio
async def test_script_master_refresh_populates_in_memory_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "data": "scripCode|tradingSymbol|exchange|instrumentType\n2475|ONGC|NC|EQ\n"
    }
    db = FakeScriptMasterDb()
    broker = FakeBrokerRouter(response)
    service = ScriptMasterService(broker_router=broker)
    monkeypatch.setenv("SCRIPT_MASTER_CACHE_TTL_HOURS", "24")

    result = await service.refresh_exchange(db, "NC", uuid.uuid4())
    resolution = await service.resolve(db, ScriptMasterLookup(symbol="ONGC", exchange="NC"), uuid.uuid4())

    assert result["records"] == 1
    assert resolution.status == RESOLVED
    assert resolution.scrip_code == 2475
    assert db.scalars_calls == 0
    assert broker.master_calls == 1


@pytest.mark.asyncio
async def test_script_master_concurrent_ensure_coalesces_exchange_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    response = {
        "data": "scripCode|tradingSymbol|exchange|instrumentType\n2475|ONGC|NC|EQ\n"
    }
    db = FakeScriptMasterDb()
    broker = FakeBrokerRouter(response, delay_seconds=0.01)
    service = ScriptMasterService(broker_router=broker)
    monkeypatch.setenv("SCRIPT_MASTER_CACHE_TTL_HOURS", "24")

    results = await asyncio.gather(
        *(service.ensure_exchange_cache(db, "NC", uuid.uuid4()) for _ in range(10))
    )

    assert results.count(True) == 1
    assert results.count(False) == 9
    assert broker.master_calls == 1
    assert service.memory_cache_info("NC")["records"] == 1


@pytest.mark.asyncio
async def test_script_master_empty_refresh_attempt_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeScriptMasterDb()
    broker = FakeBrokerRouter({})
    service = ScriptMasterService(broker_router=broker)
    monkeypatch.setenv("SCRIPT_MASTER_CACHE_TTL_HOURS", "24")

    first = await service.ensure_exchange_cache(db, "NC", uuid.uuid4())
    second = await service.ensure_exchange_cache(db, "NC", uuid.uuid4())
    resolution = await service.resolve(db, ScriptMasterLookup(symbol="ONGC", exchange="NC"), uuid.uuid4())

    assert first is True
    assert second is False
    assert resolution.status == CACHE_EMPTY
    assert broker.master_calls == 1


@pytest.mark.asyncio
async def test_live_copy_enriches_missing_scrip_code_from_script_master(monkeypatch: pytest.MonkeyPatch) -> None:
    master_account_id = uuid.uuid4()
    event = NormalizedTradeEvent(
        external_trade_id="T1",
        external_order_id="O1",
        symbol="ONGC",
        exchange="NC",
        side="B",
        quantity=1,
        price=Decimal("93.10"),
        order_type="NORMAL",
        product_type="INVESTMENT",
        raw_payload={"data": {"TradingSymbol": "ONGC"}},
        event_time=None,
        duplicate_hash="hash",
    )

    async def fake_resolve(
        db: object,
        lookup: ScriptMasterLookup,
        account_id: uuid.UUID,
        refresh_stale: bool = True,
    ) -> ScriptMasterResolution:
        assert lookup.symbol == "ONGC"
        assert lookup.exchange == "NC"
        assert account_id == master_account_id
        assert refresh_stale is False
        return ScriptMasterResolution(
            status=RESOLVED,
            message="scripCode resolved from Script Master for ONGC on NC: 2475.",
            scrip_code=2475,
        )

    monkeypatch.setattr("app.services.live_copy.script_master_service.resolve", fake_resolve)

    resolved = await live_copy_manager._resolve_missing_scrip_code(
        None,
        SimpleNamespace(id=uuid.uuid4(), master_account_id=master_account_id),
        event,
    )

    assert resolved.scrip_code == 2475
    assert resolved.scrip_code_resolution_status == RESOLVED
    assert resolved.raw_payload["script_master_resolution"]["message"].startswith("scripCode resolved from Script Master")


def test_copy_session_read_converts_stored_group_ids_to_uuid() -> None:
    group_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    response = CopySessionRead.model_validate(
        SimpleNamespace(
            id=uuid.uuid4(),
            master_account_id=uuid.uuid4(),
            status=CopySessionStatus.RUNNING,
            started_at=now,
            paused_at=None,
            resumed_at=None,
            stopped_at=None,
            last_error=None,
            active_group_ids=[str(group_id)],
            dry_run=True,
            created_by=None,
            created_at=now,
            updated_at=now,
        )
    )

    assert response.active_group_ids == [group_id]
