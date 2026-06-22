import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import redis.asyncio as redis
import websockets

from app.core.config import get_settings

logger = logging.getLogger(__name__)
STREAM_DIAGNOSTIC_LIMIT = 1000


@dataclass
class StreamConnection:
    account_id: uuid.UUID
    access_token: str
    api_key: str
    customer_id: str | None = None
    proxy_url: str | None = None
    subscriptions: set[str] = field(default_factory=set)
    task: asyncio.Task[None] | None = None
    is_connected: bool = False
    module_ready: bool = False
    ack_subscription_sent: bool = False
    connected_at: str | None = None
    disconnected_at: str | None = None
    last_message_at: str | None = None
    last_error: str | None = None
    module_ack_payload: Any | None = None
    last_sent_payload: dict[str, Any] | None = None
    sent_payloads: list[dict[str, Any]] = field(default_factory=list)
    messages_received: int = 0
    ack_messages_received: int = 0
    feed_messages_received: int = 0
    raw_messages_received: int = 0
    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    ws: Any | None = None


class SharekhanStreamManager:
    def __init__(self) -> None:
        self.connections: dict[uuid.UUID, StreamConnection] = {}

    async def connect(
        self,
        account_id: uuid.UUID,
        *,
        access_token: str,
        api_key: str,
        customer_id: str | None = None,
        proxy_url: str | None = None,
    ) -> dict[str, Any]:
        existing = self.connections.get(account_id)
        if existing and existing.task and not existing.task.done():
            existing.access_token = access_token
            existing.api_key = api_key
            existing.customer_id = customer_id or existing.customer_id
            existing.proxy_url = proxy_url
            if existing.is_connected and existing.module_ready and existing.customer_id and not existing.ack_subscription_sent:
                redis_client = redis.from_url(get_settings().redis_url, decode_responses=True)
                try:
                    await self._send_ack_subscription(existing, redis_client)
                finally:
                    await redis_client.aclose()
            return {
                "status": "already_connected" if existing.is_connected else "reconnecting",
                "module_ready": existing.module_ready,
                "ack_subscription_sent": existing.ack_subscription_sent,
            }
        connection = StreamConnection(
            account_id=account_id,
            access_token=access_token,
            api_key=api_key,
            customer_id=customer_id,
            proxy_url=proxy_url,
        )
        connection.task = asyncio.create_task(self._run(connection))
        self.connections[account_id] = connection
        return {"status": "connecting"}

    def status(self, account_id: uuid.UUID) -> dict[str, Any]:
        connection = self.connections.get(account_id)
        if not connection:
            return {
                "account_id": str(account_id),
                "status": "not_connected",
                "is_connected": False,
                "module_ready": False,
                "ack_subscription_sent": False,
            }
        task_state = "running"
        if connection.task and connection.task.done():
            task_state = "stopped"
        return {
            "account_id": str(connection.account_id),
            "status": "connected" if connection.is_connected else "reconnecting",
            "task_state": task_state,
            "is_connected": connection.is_connected,
            "module_ready": connection.module_ready,
            "ack_subscription_sent": connection.ack_subscription_sent,
            "customer_id_present": bool(connection.customer_id),
            "proxy_configured": bool(connection.proxy_url),
            "subscriptions": sorted(connection.subscriptions),
            "connected_at": connection.connected_at,
            "disconnected_at": connection.disconnected_at,
            "last_message_at": connection.last_message_at,
            "last_error": connection.last_error,
            "module_ack_payload": connection.module_ack_payload,
            "last_sent_payload": connection.last_sent_payload,
            "sent_payloads": list(connection.sent_payloads),
            "messages_received": connection.messages_received,
            "ack_messages_received": connection.ack_messages_received,
            "feed_messages_received": connection.feed_messages_received,
            "raw_messages_received": connection.raw_messages_received,
            "recent_messages": list(connection.recent_messages),
        }

    async def disconnect(self, account_id: uuid.UUID) -> dict[str, Any]:
        connection = self.connections.pop(account_id, None)
        if connection and connection.task:
            connection.task.cancel()
        return {"status": "disconnected"}

    async def subscribe(self, account_id: uuid.UUID, symbols: list[str], exchange: str) -> dict[str, Any]:
        connection = self.connections.get(account_id)
        if not connection:
            return {"status": "not_connected"}
        for symbol in symbols:
            connection.subscriptions.add(feed_subscription_value(exchange, symbol))
        await self._send_feed_subscriptions(connection, sorted(connection.subscriptions))
        return {"status": "subscribed", "symbols": sorted(connection.subscriptions)}

    async def unsubscribe(self, account_id: uuid.UUID, symbols: list[str], exchange: str) -> dict[str, Any]:
        connection = self.connections.get(account_id)
        if not connection:
            return {"status": "not_connected"}
        for symbol in symbols:
            connection.subscriptions.discard(feed_subscription_value(exchange, symbol))
        return {"status": "unsubscribed", "symbols": sorted(connection.subscriptions)}

    async def _run(self, connection: StreamConnection) -> None:
        settings = get_settings()
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        try:
            while True:
                try:
                    await self._run_once(connection, redis_client)
                except asyncio.CancelledError:
                    logger.info(f"Stream task cancelled for account {connection.account_id}")
                    raise
                except Exception as exc:
                    connection.last_error = str(exc)
                    logger.error(f"Stream connection failed for account {connection.account_id}: {exc}", extra={"account_id": str(connection.account_id)})
                    await redis_client.publish(
                        "sharekhan:stream_errors",
                        json.dumps({"account_id": str(connection.account_id), "error": str(exc)}),
                    )
                    await self._publish_stream_status(redis_client, connection, "error", error=str(exc))
                finally:
                    connection.is_connected = False
                    connection.module_ready = False
                    connection.ack_subscription_sent = False
                    connection.disconnected_at = _utc_iso()
                    connection.ws = None
                await asyncio.sleep(5)
        finally:
            connection.is_connected = False
            connection.module_ready = False
            connection.ack_subscription_sent = False
            connection.disconnected_at = _utc_iso()
            connection.ws = None
            await redis_client.aclose()

    async def _run_once(self, connection: StreamConnection, redis_client: redis.Redis) -> None:
        settings = get_settings()
        stream_url = f"{settings.sharekhan_ws_url}?{urlencode({'ACCESS_TOKEN': connection.access_token, 'API_KEY': connection.api_key})}"
        logger.info(f"Connecting websocket for account {connection.account_id}...")
        async with websockets.connect(stream_url, ping_interval=20, ping_timeout=20) as ws:
            connection.is_connected = True
            connection.connected_at = _utc_iso()
            connection.disconnected_at = None
            connection.last_error = None
            connection.ws = ws
            logger.info(f"Websocket connected for account {connection.account_id}")
            await self._publish_stream_status(redis_client, connection, "connected")
            await self._send_module_subscription(connection, redis_client)
            await self._wait_for_module_ack(connection, redis_client)
            await self._send_ack_subscription(connection, redis_client)
            await self._send_feed_subscriptions(connection, sorted(connection.subscriptions), redis_client=redis_client)
            async for message in ws:
                await self._publish_stream_message(redis_client, connection, message)

    async def _send_json(self, connection: StreamConnection, payload: dict[str, Any]) -> bool:
        if not connection.ws or not connection.is_connected:
            return False
        await connection.ws.send(json.dumps(payload))
        connection.last_sent_payload = payload
        connection.sent_payloads.append(
            {
                "type": str(payload.get("action", "raw")),
                "sent_at": _utc_iso(),
                "payload": payload,
            }
        )
        connection.sent_payloads = connection.sent_payloads[-STREAM_DIAGNOSTIC_LIMIT:]
        logger.info(
            "Sharekhan websocket sent %s frame for account %s",
            payload.get("action", "raw"),
            connection.account_id,
        )
        return True

    async def _send_module_subscription(self, connection: StreamConnection, redis_client: redis.Redis) -> None:
        payload = module_subscription_payload()
        sent = await self._send_json(connection, payload)
        await self._publish_stream_status(redis_client, connection, "module_subscription_sent", payload=payload, sent=sent)

    async def _wait_for_module_ack(self, connection: StreamConnection, redis_client: redis.Redis) -> None:
        if not connection.ws:
            return
        deadline = asyncio.get_running_loop().time() + 10
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                await self._publish_module_subscription_timeout(redis_client, connection)
                return
            try:
                message = await asyncio.wait_for(connection.ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                await self._publish_module_subscription_timeout(redis_client, connection)
                return

            payload = _json_or_raw(message)
            message_type = _record_stream_message(connection, payload)
            await redis_client.publish(
                "sharekhan:ticks",
                json.dumps(
                    {
                        "account_id": str(connection.account_id),
                        "type": message_type,
                        "payload": payload,
                    }
                ),
            )

            if _module_subscription_succeeded(payload):
                connection.module_ready = True
                connection.module_ack_payload = payload
                connection.last_error = None
                await self._publish_stream_status(
                    redis_client,
                    connection,
                    "module_subscription_ack",
                    payload=connection.module_ack_payload,
                    module_ready=True,
                )
                return

            if _is_module_subscription_response(payload):
                connection.module_ready = False
                connection.module_ack_payload = payload
                connection.last_error = "Sharekhan module subscription did not confirm feed+ack readiness"
                await self._publish_stream_status(
                    redis_client,
                    connection,
                    "module_subscription_ack",
                    payload=connection.module_ack_payload,
                    module_ready=False,
                    error=connection.last_error,
                )
                return

            await self._publish_stream_status(
                redis_client,
                connection,
                "module_subscription_waiting",
                payload=payload,
                message_type=message_type,
            )

    async def _send_ack_subscription(self, connection: StreamConnection, redis_client: redis.Redis) -> None:
        if connection.ack_subscription_sent:
            return
        if not connection.customer_id:
            connection.last_error = "Sharekhan customerId is missing; ack subscription was not sent"
            await self._publish_stream_status(redis_client, connection, "ack_subscription_skipped", error=connection.last_error)
            return
        if not connection.module_ready:
            connection.last_error = "Sharekhan module subscription did not confirm feed+ack readiness"
            await self._publish_stream_status(redis_client, connection, "ack_subscription_blocked", error=connection.last_error)
            return
        payload = ack_subscription_payload(connection.customer_id)
        sent = await self._send_json(connection, payload)
        connection.ack_subscription_sent = sent
        await self._publish_stream_status(redis_client, connection, "ack_subscription_sent", payload=payload, sent=sent)

    async def _send_feed_subscriptions(
        self,
        connection: StreamConnection,
        values: list[str],
        feed_key: str = "ltp",
        redis_client: redis.Redis | None = None,
    ) -> None:
        if connection.module_ready and values:
            payload = feed_subscription_payload(values, feed_key=feed_key)
            sent = await self._send_json(connection, payload)
            if redis_client:
                await self._publish_stream_status(redis_client, connection, "feed_subscription_sent", payload=payload, sent=sent)

    async def _publish_stream_message(
        self,
        redis_client: redis.Redis,
        connection: StreamConnection,
        message: Any,
    ) -> None:
        payload = _json_or_raw(message)
        message_type = _record_stream_message(connection, payload)
        await redis_client.publish(
            "sharekhan:ticks",
            json.dumps(
                {
                    "account_id": str(connection.account_id),
                    "type": message_type,
                    "payload": payload,
                }
            ),
        )
        if _module_subscription_succeeded(payload):
            connection.module_ready = True
            connection.module_ack_payload = payload
            if connection.last_error == "Sharekhan module subscription did not confirm feed+ack readiness":
                connection.last_error = None
            await self._publish_stream_status(
                redis_client,
                connection,
                "module_subscription_ack",
                payload=payload,
                module_ready=True,
            )
            if connection.customer_id and not connection.ack_subscription_sent:
                await self._send_ack_subscription(connection, redis_client)

    async def _publish_module_subscription_timeout(
        self,
        redis_client: redis.Redis,
        connection: StreamConnection,
    ) -> None:
        await redis_client.publish(
            "sharekhan:stream_errors",
            json.dumps({"account_id": str(connection.account_id), "error": "Sharekhan stream module subscription timed out"}),
        )
        connection.last_error = "Sharekhan stream module subscription timed out"
        await self._publish_stream_status(redis_client, connection, "module_subscription_timeout")

    async def _publish_stream_status(
        self,
        redis_client: redis.Redis,
        connection: StreamConnection,
        event: str,
        **extra: Any,
    ) -> None:
        await redis_client.publish(
            "sharekhan:ticks",
            json.dumps(
                {
                    "account_id": str(connection.account_id),
                    "type": "stream_status",
                    "payload": {
                        "event": event,
                        "timestamp": _utc_iso(),
                        "is_connected": connection.is_connected,
                        "module_ready": connection.module_ready,
                        "ack_subscription_sent": connection.ack_subscription_sent,
                        **extra,
                    },
                }
            ),
        )


def feed_subscription_value(exchange: str, symbol: str) -> str:
    return f"{exchange.strip().upper()}{str(symbol).strip()}"


def module_subscription_payload() -> dict[str, Any]:
    return {"action": "subscribe", "key": ["feed", "ack"], "value": [""]}


def feed_subscription_payload(values: list[str], *, feed_key: str = "ltp") -> dict[str, Any]:
    return {"action": "feed", "key": [feed_key], "value": values}


def ack_subscription_payload(customer_id: str) -> dict[str, Any]:
    return {"action": "ack", "key": [""], "value": [customer_id]}


def _record_stream_message(connection: StreamConnection, payload: Any) -> str:
    message_type = stream_message_type(payload)
    connection.last_message_at = _utc_iso()
    connection.messages_received += 1
    if message_type == "ack":
        connection.ack_messages_received += 1
    elif message_type == "feed":
        connection.feed_messages_received += 1
    else:
        connection.raw_messages_received += 1
    connection.recent_messages.append(
        {
            "type": message_type,
            "received_at": connection.last_message_at,
            "payload": payload,
        }
    )
    connection.recent_messages = connection.recent_messages[-STREAM_DIAGNOSTIC_LIMIT:]
    return message_type


def _json_or_raw(message: Any) -> Any:
    if isinstance(message, (dict, list)):
        return message
    if isinstance(message, bytes):
        message = message.decode("utf-8", errors="replace")
    if isinstance(message, str):
        try:
            return json.loads(message)
        except ValueError:
            return message
    return message


def _module_subscription_succeeded(message: Any) -> bool:
    payload = _json_or_raw(message)
    if not isinstance(payload, dict):
        return False
    try:
        status_ok = int(str(payload.get("status", "")).strip()) == 100
    except ValueError:
        status_ok = False
    normalized_data = "".join(ch for ch in str(payload.get("data", "")).upper() if ch.isalnum())
    return status_ok and "SUCCESSFEED" in normalized_data and "SUCCESSACK" in normalized_data


def _is_module_subscription_response(message: Any) -> bool:
    payload = _json_or_raw(message)
    if not isinstance(payload, dict):
        return False
    return str(payload.get("message", "")).strip().lower() == "subscribe"


def stream_message_type(payload: Any) -> str:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, dict):
            data_keys = {str(key).lower() for key in data}
            if "sharekhanorderid" in data_keys or "ackstate" in data_keys or "tradeid" in data_keys:
                return "ack"
            if "ltp" in data_keys or "scripcode" in data_keys or "exchangecode" in data_keys:
                return "feed"
        message = payload.get("message")
        if isinstance(message, str):
            return message
    return "raw"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


stream_manager = SharekhanStreamManager()
