import uuid
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.engine import CopyTradingEngine
from app.risk import (
    CopyAccount,
    CopySettings,
    CopyTarget,
    MasterOrder,
    RiskRejected,
    calculate_quantity,
    idempotency_key,
    validate_risk,
)


def _master() -> MasterOrder:
    return MasterOrder(
        id=uuid.uuid4(),
        broker_order_id="M1",
        exchange="NC",
        scrip_code="2475",
        trading_symbol="ONGC",
        transaction_type="B",
        quantity=100,
        price=Decimal("150"),
    )


def _account() -> CopyAccount:
    return CopyAccount(
        id=uuid.uuid4(),
        customer_id="C1",
        login_id="L1",
        is_active=True,
        has_token=True,
        capital=Decimal("100000"),
    )


def test_copy_quantity_calculation_modes() -> None:
    master = _master()
    account = _account()
    assert calculate_quantity(master, CopySettings(sizing_mode="SAME_QTY"), account) == 100
    assert calculate_quantity(master, CopySettings(sizing_mode="MULTIPLIER", multiplier=Decimal("0.5")), account) == 50
    assert calculate_quantity(master, CopySettings(sizing_mode="FIXED_QTY", fixed_qty=25), account) == 25
    assert (
        calculate_quantity(
            master,
            CopySettings(sizing_mode="PERCENT_CAPITAL", capital_percent=Decimal("15")),
            account,
        )
        == 100
    )


def test_risk_rule_validation_blocks_symbol() -> None:
    target = CopyTarget(_account(), CopySettings(blocked_symbols=["ONGC"]))
    with pytest.raises(RiskRejected, match="symbol is blocked"):
        validate_risk(
            _master(),
            target,
            now=datetime(2026, 6, 1, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )


def test_risk_rule_validation_allows_valid_order() -> None:
    target = CopyTarget(_account(), CopySettings(max_qty=100, max_order_value=Decimal("20000")))
    assert (
        validate_risk(
            _master(),
            target,
            now=datetime(2026, 6, 1, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")),
        )
        == 100
    )


def test_idempotency_key_is_stable() -> None:
    master_id = uuid.uuid4()
    account_id = uuid.uuid4()
    assert idempotency_key(master_id, account_id, "NEW") == idempotency_key(master_id, account_id, "new")


@pytest.mark.asyncio
async def test_duplicate_idempotency_prevention() -> None:
    master = _master()
    account = _account()
    target = CopyTarget(account, CopySettings())
    saved = []

    async def place_order(_account_id, _payload):
        raise AssertionError("duplicate order should not be placed")

    async def exists(_key):
        return True

    async def save(result, _request, _response):
        saved.append(result)

    engine = CopyTradingEngine(place_order=place_order, order_exists=exists, save_copy_order=save)
    results = await engine.process_master_order(master, [target], enforce_market_hours=False)
    assert results[0].status == "SKIPPED"
    assert saved[0].error_message == "duplicate idempotency key"


@pytest.mark.asyncio
async def test_copy_worker_retry_behavior() -> None:
    master = _master()
    target = CopyTarget(_account(), CopySettings())
    attempts = {"count": 0}
    saved = []

    async def place_order(_account_id, _payload):
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RuntimeError("temporary broker failure")
        return {"normalized": {"broker_order_id": "COPY-1"}}

    async def exists(_key):
        return False

    async def save(result, _request, _response):
        saved.append(result)

    async def no_sleep(_seconds):
        return None

    engine = CopyTradingEngine(
        place_order=place_order,
        order_exists=exists,
        save_copy_order=save,
        max_retries=3,
        sleep=no_sleep,
    )
    results = await engine.process_master_order(master, [target], enforce_market_hours=False)
    assert results[0].status == "SUCCESS"
    assert results[0].retry_count == 2
    assert attempts["count"] == 3
    assert saved[0].broker_order_id == "COPY-1"

