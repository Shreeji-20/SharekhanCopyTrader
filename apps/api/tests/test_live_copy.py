from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest

from app.models import CopySessionStatus, PriceMode, SizingMode
from app.schemas import CopySessionRead
from app.services.live_copy import (
    CopySkip,
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
        isin=isin,
    )


def test_normalize_sharekhan_ack_ignores_order_confirmation_without_trade_qty() -> None:
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

    assert normalize_sharekhan_ack(payload) is None


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
        "data": "scripCode|tradingSymbol|exchange|instrumentType|isin\n2475|ONGC|NC|EQ|INE213A01029\n"
    }

    rows = normalize_script_master_response(response, "NC")

    assert len(rows) == 1
    assert rows[0].scrip_code == "2475"
    assert rows[0].trading_symbol == "ONGC"
    assert rows[0].isin == "INE213A01029"


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

    async def fake_resolve(db: object, lookup: ScriptMasterLookup, account_id: uuid.UUID) -> ScriptMasterResolution:
        assert lookup.symbol == "ONGC"
        assert lookup.exchange == "NC"
        assert account_id == master_account_id
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
