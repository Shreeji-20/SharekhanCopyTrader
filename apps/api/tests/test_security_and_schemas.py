from decimal import Decimal
from types import SimpleNamespace
import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models import AccountType, Broker
from app.routers.accounts import account_response, stored_sharekhan_profile_response
from app.core.config import get_settings
from app.encryption import decrypt_secret, encrypt_secret
from app.schemas import (
    BrokerAccountCreate,
    BrokerAccountUpdate,
    CopyGroupMemberCreate,
    CopySettingPatch,
    SharekhanCallbackExchange,
    SharekhanOrderPayload,
    SharekhanWsSubscription,
)
from app.security import mask_secret
from app.services.script_master_preload import script_master_preload_exchanges_from_profile


def test_token_masking() -> None:
    assert mask_secret("abcdefghijklmnopqrstuvwxyz") == "abcd********wxyz"
    assert mask_secret(None) is None


def test_account_secret_encryption_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    get_settings.cache_clear()
    ciphertext = encrypt_secret("sharekhan-api-key")
    assert ciphertext != "sharekhan-api-key"
    assert decrypt_secret(ciphertext) == "sharekhan-api-key"


def test_sharekhan_callback_can_resolve_by_state_without_browser_account_id() -> None:
    payload = SharekhanCallbackExchange(state="12345678", request_token="request-token")

    assert payload.account_id is None
    assert payload.state == "12345678"


def test_script_master_preload_exchange_selection_uses_profile_and_config() -> None:
    exchanges = script_master_preload_exchanges_from_profile(
        {"exchanges": ["nc", "NF", " "]},
        ["NC", "BC"],
    )

    assert exchanges == ["NC", "NF", "BC"]


def test_script_master_preload_exchange_setting_parses_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCRIPT_MASTER_PRELOAD_EXCHANGES", "nc,nf,bc")
    get_settings.cache_clear()
    try:
        assert get_settings().script_master_preload_exchange_codes == ["NC", "NF", "BC"]
    finally:
        get_settings.cache_clear()


def test_account_response_survives_unreadable_encrypted_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "old-secret")
    get_settings.cache_clear()
    encrypted_api_key = encrypt_secret("sharekhan-api-key")
    encrypted_secret_key = encrypt_secret("sharekhan-secure-key")

    monkeypatch.setenv("APP_SECRET_KEY", "new-secret")
    get_settings.cache_clear()
    now = datetime.now(timezone.utc)
    response = account_response(
        SimpleNamespace(
            id=uuid.uuid4(),
            broker=Broker.SHAREKHAN,
            account_name="Locked Account",
            customer_id=None,
            login_id=None,
            api_key=encrypted_api_key,
            secret_key=encrypted_secret_key,
            vendor_key=None,
            proxy_scheme=None,
            proxy_host=None,
            proxy_port=None,
            proxy_username=None,
            proxy_password=None,
            request_token=None,
            access_token=None,
            refresh_token=None,
            token_expires_at=None,
            account_type=AccountType.MASTER,
            is_active=True,
            last_connected_at=None,
            created_at=now,
            updated_at=now,
        )
    )

    assert response.credentials_readable is False
    assert response.api_key == "UNREADABLE"
    assert response.secret_key == "UNREADABLE"


def test_stored_sharekhan_profile_response_uses_existing_account_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "profile-secret")
    get_settings.cache_clear()
    now = datetime.now(timezone.utc)
    response = stored_sharekhan_profile_response(
        SimpleNamespace(
            id=uuid.uuid4(),
            broker=Broker.SHAREKHAN,
            customer_id="CUSTOMER1",
            login_id="LOGIN1",
            request_token=encrypt_secret("request-token"),
            access_token=encrypt_secret("access-token"),
            refresh_token=None,
            token_expires_at=now,
        )
    )

    assert response["ok"] is True
    assert response["customer_id"] == "CUSTOMER1"
    assert response["login_id"] == "LOGIN1"
    assert response["access_token"] == "acce********oken"
    assert response["raw_status"] == "stored"


def test_order_payload_validation_for_new_order() -> None:
    payload = SharekhanOrderPayload(
        customerId="CUSTOMER_ID",
        scripCode=2475,
        tradingSymbol="ongc",
        exchange="nc",
        transactionType="B",
        quantity=1,
        disclosedQty=0,
        price=Decimal("149.5"),
        triggerPrice=Decimal("0"),
        channelUser="LOGIN_ID",
    )
    assert payload.tradingSymbol == "ONGC"
    assert payload.exchange == "NC"
    assert payload.requestType == "NEW"


def test_order_payload_requires_order_id_for_modify() -> None:
    with pytest.raises(ValidationError):
        SharekhanOrderPayload(
            customerId="CUSTOMER_ID",
            scripCode=2475,
            tradingSymbol="ONGC",
            exchange="NC",
            transactionType="B",
            quantity=1,
            price=Decimal("149.5"),
            channelUser="LOGIN_ID",
            requestType="MODIFY",
        )


def test_broker_account_proxy_validation() -> None:
    payload = BrokerAccountCreate(
        account_name="Copy Account",
        api_key="api-key",
        secret_key="secret-key",
        account_type="COPY",
        proxy_scheme="http",
        proxy_host=" proxy.local ",
        proxy_port=8080,
        proxy_username="proxy-user",
        proxy_password="proxy-pass",
    )
    assert payload.proxy_scheme == "http"
    assert payload.proxy_host == "proxy.local"
    assert payload.proxy_port == 8080

    with pytest.raises(ValidationError):
        BrokerAccountCreate(
            account_name="Copy Account",
            api_key="api-key",
            secret_key="secret-key",
            account_type="COPY",
            proxy_scheme="http",
            proxy_port=8080,
        )


def test_broker_account_can_be_created_with_only_sharekhan_api_credentials() -> None:
    payload = BrokerAccountCreate(
        account_name="Master Account",
        api_key="api-key",
        secret_key="secure-key",
        account_type="MASTER",
    )
    assert payload.customer_id is None
    assert payload.login_id is None


def test_broker_account_update_can_clear_optional_sharekhan_identity() -> None:
    payload = BrokerAccountUpdate(customer_id="  ", login_id=" LOGIN123 ", vendor_key="")

    assert payload.customer_id is None
    assert payload.login_id == "LOGIN123"
    assert payload.vendor_key is None


def test_sharekhan_ws_subscription_normalizes_exchange_and_symbols() -> None:
    payload = SharekhanWsSubscription(exchange=" nc ", symbols=[" 2885 ", ""])

    assert payload.exchange == "NC"
    assert payload.symbols == ["2885"]


def test_copy_setting_validation_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        CopySettingPatch(min_qty=10, max_qty=5)

    with pytest.raises(ValidationError):
        CopySettingPatch(sizing_mode="FIXED_QTY")


def test_copy_group_member_create_accepts_group_scoped_risk_setting() -> None:
    payload = CopyGroupMemberCreate(
        copy_account_id=uuid.uuid4(),
        copy_setting={
            "sizing_mode": "MULTIPLIER",
            "multiplier": Decimal("2"),
            "allowed_symbols": [" ongc ", "ONGC"],
            "allowed_transaction_types": ["b"],
            "max_trades_per_day": 3,
        },
    )

    assert payload.copy_setting is not None
    assert payload.copy_setting.allowed_symbols == ["ONGC"]
    assert payload.copy_setting.allowed_transaction_types == ["B"]
    assert payload.copy_setting.max_trades_per_day == 3
