import asyncio
import json
import uuid

import pytest

from app.brokers.sharekhan.client import SharekhanRawClient
from app.brokers.sharekhan.token import convert_request_token_for_access_token, encrypt_final_token
from app.core.config import get_settings
from app.db import SharekhanAccount, _decrypt_account_secret
from app.main import _proxy_url
from app.security import encrypt_secret
from app.websocket_manager import (
    SharekhanStreamManager,
    StreamConnection,
    _module_subscription_succeeded,
    ack_subscription_payload,
    feed_subscription_payload,
    feed_subscription_value,
    module_subscription_payload,
    stream_message_type,
)


class FakeRedis:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


class FakeWebSocket:
    def __init__(self, messages: list[str]) -> None:
        self.messages = messages
        self.sent: list[str] = []

    async def recv(self) -> str:
        if not self.messages:
            await asyncio.sleep(30)
            return ""
        return self.messages.pop(0)

    async def send(self, message: str) -> None:
        self.sent.append(message)


def test_raw_sharekhan_route_url_building() -> None:
    client = SharekhanRawClient(api_key="api", base_url="https://api.sharekhan.com")
    assert (
        client.build_url("order_trades", exchange="NC", customerId="C1", orderId="O1")
        == "https://api.sharekhan.com/skapi/services/reports/NC/C1/O1/trades"
    )


def test_header_building_with_optional_vendor_key() -> None:
    client = SharekhanRawClient(
        api_key="api-key",
        access_token="access-token",
        vendor_key="vendor-key",
    )
    headers = client.build_headers()
    assert headers["api-key"] == "api-key"
    assert headers["access-token"] == "access-token"
    assert headers["vendor-key"] == "vendor-key"
    assert headers["Content-Type"] == "application/json"


def test_header_building_omits_empty_vendor_key() -> None:
    client = SharekhanRawClient(api_key="api-key", access_token="access-token")
    assert "vendor-key" not in client.build_headers()


def test_login_url_includes_state_when_supplied() -> None:
    client = SharekhanRawClient(api_key="api-key", vendor_key="vendor-key")
    url = client.generate_login_url(state="12345")

    assert "api_key=api-key" in url
    assert "vendor_key=vendor-key" in url
    assert "state=12345" in url


def test_proxy_url_is_bound_to_client() -> None:
    client = SharekhanRawClient(api_key="api-key", proxy_url="http://proxy.local:8080")
    assert client.proxy_url == "http://proxy.local:8080"


def test_structured_proxy_details_are_composed() -> None:
    account = SharekhanAccount(
        id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        customer_id="C1",
        login_id="L1",
        api_key="api-key",
        secret_key="secret-key",
        vendor_key=None,
        proxy_scheme="http",
        proxy_host="proxy.local",
        proxy_port=8080,
        proxy_username="user name",
        proxy_password="p@ss",
        sharekhan_login_state=None,
        request_token=None,
        access_token=None,
        refresh_token=None,
        token_expires_at=None,
    )
    assert _proxy_url(account) == "http://user%20name:p%40ss@proxy.local:8080"


def test_unreadable_account_secret_returns_operator_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "old-secret")
    get_settings.cache_clear()
    encrypted_value = encrypt_secret("sharekhan-api-key")

    monkeypatch.setenv("APP_SECRET_KEY", "new-secret")
    get_settings.cache_clear()
    with pytest.raises(ValueError, match="Re-save the account credentials"):
        _decrypt_account_secret(encrypted_value, "API key")


def test_unreadable_optional_token_can_be_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_SECRET_KEY", "old-secret")
    get_settings.cache_clear()
    encrypted_value = encrypt_secret("access-token")

    monkeypatch.setenv("APP_SECRET_KEY", "new-secret")
    get_settings.cache_clear()
    assert _decrypt_account_secret(encrypted_value, "access token", required=False) is None


@pytest.mark.asyncio
async def test_sharekhan_access_token_request_sends_final_token_and_version() -> None:
    client = SharekhanRawClient(api_key="api-key", vendor_key="vendor-key")
    captured: dict[str, object] = {}

    async def fake_request(method: str, route_name: str, **kwargs: object) -> dict[str, object]:
        captured["method"] = method
        captured["route_name"] = route_name
        captured["json"] = kwargs["json"]
        return {"status": 200, "message": "access_token", "data": {"token": "access-token"}}

    client._request = fake_request  # type: ignore[method-assign]

    await client.exchange_access_token(final_request_token="FINAL_ENCRYPTED_TOKEN", state="12345", version_id="1005")

    assert captured["method"] == "POST"
    assert captured["route_name"] == "access_token"
    assert captured["json"] == {
        "apiKey": "api-key",
        "requestToken": "FINAL_ENCRYPTED_TOKEN",
        "state": "12345",
        "versionId": "1005",
        "vendorkey": "vendor-key",
    }


def test_sharekhan_request_token_conversion_swaps_decrypted_payload() -> None:
    secure_key = "12345678901234567890123456789012"
    raw_request_token = encrypt_final_token("request-key|CUSTOMER1", secure_key)

    converted = convert_request_token_for_access_token(raw_request_token, secure_key)

    assert converted.request_key == "request-key"
    assert converted.customer_id == "CUSTOMER1"
    assert converted.final_encrypted_token != raw_request_token
    assert convert_request_token_for_access_token(converted.final_encrypted_token, secure_key).request_key == "CUSTOMER1"


def test_sharekhan_websocket_payload_builders() -> None:
    assert module_subscription_payload() == {"action": "subscribe", "key": ["feed", "ack"], "value": [""]}
    assert feed_subscription_value("nc", "2885") == "NC2885"
    assert feed_subscription_payload(["NC2885"]) == {"action": "feed", "key": ["ltp"], "value": ["NC2885"]}
    assert ack_subscription_payload("CUSTOMER1") == {"action": "ack", "key": [""], "value": ["CUSTOMER1"]}


def test_sharekhan_stream_message_type_detects_ack_and_feed() -> None:
    assert stream_message_type({"data": {"SharekhanOrderID": "O1", "AckState": "NewOrderConfirmation"}}) == "ack"
    assert stream_message_type({"data": {"sharekhanOrderId": "O1", "ackState": "NewOrderConfirmation"}}) == "ack"
    assert stream_message_type({"data": {"exchangeCode": "NC", "scripCode": 2885, "ltp": 100}}) == "feed"


def test_sharekhan_module_subscription_success_is_case_insensitive() -> None:
    assert _module_subscription_succeeded({"status": 100, "data": "successFEED,successACK"}) is True
    assert _module_subscription_succeeded({"status": 100, "data": "successFeed,successAck"}) is True
    assert _module_subscription_succeeded({"status": 100, "data": "success Feed, success Ack"}) is True
    assert _module_subscription_succeeded({"status": 100, "data": "success FEED,success ACK"}) is True
    assert _module_subscription_succeeded({"status": "100", "data": "success FEED,success ACK"}) is True


@pytest.mark.asyncio
async def test_sharekhan_module_ack_wait_ignores_initial_connect_message() -> None:
    connection = StreamConnection(
        account_id=uuid.uuid4(),
        access_token="access-token",
        api_key="api-key",
        customer_id="CUSTOMER1",
    )
    connection.is_connected = True
    connection.ws = FakeWebSocket(
        [
            json.dumps({"status": 100, "message": "connect", "data": "Connected session-id"}),
            json.dumps({"status": 100, "message": "subscribe", "data": "success FEED,success ACK"}),
        ]
    )
    redis = FakeRedis()

    await SharekhanStreamManager()._wait_for_module_ack(connection, redis)  # type: ignore[arg-type]

    assert connection.module_ready is True
    assert connection.module_ack_payload == {"status": 100, "message": "subscribe", "data": "success FEED,success ACK"}
    assert connection.last_error is None
    assert connection.messages_received == 2
    assert [message["type"] for message in connection.recent_messages] == ["connect", "subscribe"]

    await SharekhanStreamManager()._send_ack_subscription(connection, redis)  # type: ignore[arg-type]

    assert connection.ack_subscription_sent is True
    assert [json.loads(message) for message in connection.ws.sent] == [ack_subscription_payload("CUSTOMER1")]  # type: ignore[union-attr]
    assert connection.last_sent_payload == ack_subscription_payload("CUSTOMER1")
    assert connection.sent_payloads[-1]["payload"] == ack_subscription_payload("CUSTOMER1")


def test_sharekhan_stream_status_for_missing_connection() -> None:
    account_id = uuid.uuid4()
    assert SharekhanStreamManager().status(account_id) == {
        "account_id": str(account_id),
        "status": "not_connected",
        "is_connected": False,
        "module_ready": False,
        "ack_subscription_sent": False,
    }


def test_sharekhan_stream_status_returns_retained_history() -> None:
    manager = SharekhanStreamManager()
    account_id = uuid.uuid4()
    connection = StreamConnection(account_id=account_id, access_token="access-token", api_key="api-key")
    connection.sent_payloads = [
        {"type": "ack", "sent_at": f"sent-{index}", "payload": {"index": index}}
        for index in range(12)
    ]
    connection.recent_messages = [
        {"type": "ack", "received_at": f"received-{index}", "payload": {"index": index}}
        for index in range(12)
    ]
    manager.connections[account_id] = connection

    status = manager.status(account_id)

    assert len(status["sent_payloads"]) == 12
    assert len(status["recent_messages"]) == 12
