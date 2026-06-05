# Broker Router

The broker-router lives in `apps/broker-router`. It is an internal FastAPI service that isolates raw Sharekhan integration from the main API and worker.

## Runtime

| Item | Value |
| --- | --- |
| App entry | `apps/broker-router/app/main.py` |
| ASGI server | `uvicorn app.main:app --host 0.0.0.0 --port 8001` |
| Dockerfile | `apps/broker-router/Dockerfile` |
| Public port in compose | `8001` |
| Database use | Reads/decrypts broker accounts and stores profile/access-token results. |
| Redis use | Publishes WebSocket stream messages and stream errors. |

## Core Modules

| File | Purpose |
| --- | --- |
| `app/main.py` | FastAPI routes for login, token exchange, orders, reports, holdings, master data, historical data, and WebSocket session controls. |
| `app/brokers/sharekhan/client.py` | Raw Sharekhan HTTP client and order response normalizer. |
| `app/db.py` | Partial `broker_accounts` table, account loading, token storage. |
| `app/security.py` | AES-GCM encrypt/decrypt and secret masking, matching main API behavior. |
| `app/limiter.py` | In-memory per-client rate limiter. |
| `app/websocket_manager.py` | Sharekhan WebSocket connection manager and Redis publisher. |
| `app/schemas.py` | Request and response schemas. |

## Account Loading

Broker-router receives account IDs from the main API or worker. It then:

1. Loads the row from `broker_accounts`.
2. Decrypts `api_key`, `secret_key`, `vendor_key`, structured proxy fields, `request_token`, `access_token`, and `refresh_token`.
3. Constructs a `SharekhanRawClient`.

Only a partial SQLAlchemy Core table is declared because broker-router needs only the credential/token columns.

## Rate Limiting

Every route has a FastAPI dependency on `rate_limiter`.

Current behavior:

- In-memory sliding window by `request.client.host`.
- Default limit is `120` requests per minute.
- Exceeding the limit returns `429 Broker rate limit exceeded`.

This limiter is per process. It does not coordinate across multiple broker-router replicas.

## Health

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Returns service status and current `paper_trading_mode`. |

Example:

```json
{"status": "ok", "paper_trading_mode": true}
```

## Token And Login Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/sharekhan/login-url` | Builds a Sharekhan login URL from encrypted account credentials. |
| `GET` | `/sharekhan/accounts/{account_id}/profile` | Uses the stored raw request token to fetch Sharekhan profile/access-token data and store returned identity/token values. |
| `POST` | `/sharekhan/token/exchange` | Manual exchange helper that accepts a request token, fetches profile/access-token data, and stores returned identity/token values. |

`/sharekhan/login-url` request:

```json
{
  "account_id": "00000000-0000-0000-0000-000000000000",
  "state": "12345678"
}
```

`state` is optional for the broker-router schema, but the main API supplies a random numeric state for normal web login. Sharekhan returns this state to the frontend callback when it includes a state at all.

`/sharekhan/token/exchange` request:

```json
{
  "account_id": "00000000-0000-0000-0000-000000000000",
  "request_token": "REQUEST_TOKEN"
}
```

Access-token exchange sends this payload to Sharekhan's `/skapi/services/access/token` route:

```json
{
  "apiKey": "SHAREKHAN_API_KEY",
  "requestToken": "FINAL_ENCRYPTED_TOKEN",
  "state": "12345678",
  "versionId": "SHAREKHAN_VERSION_ID"
}
```

Broker-router creates `FINAL_ENCRYPTED_TOKEN` by decrypting the raw callback request token with the account Secure Key, swapping `key|customerId` to `customerId|key`, and encrypting the swapped value again.

When a vendor key is configured, broker-router also includes `vendorkey`.

Access-token exchange stores:

- `broker_accounts.access_token`
- `broker_accounts.refresh_token`
- `broker_accounts.token_expires_at`
- `broker_accounts.last_connected_at`
- `broker_accounts.customer_id`, when returned as `data.customerId`
- `broker_accounts.login_id`, when returned as `data.loginId` or defaulting to the customer ID

Sharekhan login/token flow:

1. Account setup needs the Sharekhan API Key and Secure Key. Vendor key is optional.
2. The main API asks broker-router to build the login URL with `api_key`, optional `vendor_key`, and a random numeric state.
3. The frontend opens that URL either from an account accordion item or from the account-list batch login action. When selected accounts exist, batch login uses only those accounts; otherwise it opens every account.
4. After the user logs in with Sharekhan, Sharekhan redirects to the configured frontend callback URL with a `request_token`.
5. The main API saves the raw `request_token` on the matching account.
6. The main API immediately calls broker-router's token exchange endpoint.
7. Broker-router decrypts the raw callback token, converts `key|customerId` into `customerId|key`, encrypts that swapped value into `FinalEncryptedToken`, sends it as `requestToken` with `apiKey`, `state`, and `versionId`, then stores the returned access token/profile fields.
8. The account accordion later displays stored masked fields from the main API; it does not call broker-router or Sharekhan's access-token endpoint again.

## Order Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/sharekhan/accounts/{account_id}/orders/place` | Places a `NEW` order or returns a paper response. |
| `POST` | `/sharekhan/accounts/{account_id}/orders/modify` | Modifies an order or returns a paper response. |
| `POST` | `/sharekhan/accounts/{account_id}/orders/cancel` | Cancels an order or returns a paper response. |

Validation:

- Place requires `requestType=NEW`.
- Modify and cancel require `orderId`.
- Broker data/order endpoints require a stored access token unless paper order simulation returns first.

Response model:

```json
{
  "ok": true,
  "data": {},
  "normalized": {
    "broker_order_id": "ORDER_ID",
    "status": "STATUS",
    "message": "MESSAGE",
    "raw": {}
  },
  "paper_trading": false
}
```

## Paper Trading Behavior

When `PAPER_TRADING_MODE=true`, place/modify/cancel endpoints do not call Sharekhan. They return a synthetic response:

```json
{
  "ok": true,
  "data": {
    "orderId": "PAPER-ABC123...",
    "status": "PAPER_ACCEPTED",
    "message": "Paper trading mode is enabled; no broker order was sent.",
    "accountId": "ACCOUNT_ID",
    "requestType": "NEW",
    "receivedAt": "..."
  },
  "normalized": {
    "broker_order_id": "PAPER-ABC123...",
    "status": "PAPER_ACCEPTED",
    "message": "Paper trading mode is enabled; no broker order was sent.",
    "raw": {}
  },
  "paper_trading": true
}
```

Paper mode only short-circuits order mutation endpoints. Funds, reports, trades, holdings, order details, master data with an account, historical data with an account, and WebSocket connection still require a valid access token.

## Broker Data Endpoints

| Method | Path | Sharekhan route |
| --- | --- | --- |
| `GET` | `/sharekhan/accounts/{account_id}/profile` | `/skapi/services/access/token` |
| `GET` | `/sharekhan/accounts/{account_id}/funds/{exchange}` | `/skapi/services/limitstmt/{exchange}/{customerId}` |
| `GET` | `/sharekhan/accounts/{account_id}/reports` | `/skapi/services/reports/{customerId}` |
| `GET` | `/sharekhan/accounts/{account_id}/trades` | `/skapi/services/trades/{customerId}` |
| `GET` | `/sharekhan/accounts/{account_id}/orders/{exchange}/{order_id}` | `/skapi/services/reports/{exchange}/{customerId}/{orderId}` |
| `GET` | `/sharekhan/accounts/{account_id}/orders/{exchange}/{order_id}/trades` | `/skapi/services/reports/{exchange}/{customerId}/{orderId}/trades` |
| `GET` | `/sharekhan/accounts/{account_id}/holdings` | `/skapi/services/holdings/{customerId}` |
| `GET` | `/sharekhan/master/{exchange}` | `/skapi/services/master/{exchange}` |
| `GET` | `/sharekhan/historical/{exchange}/{scripcode}/{interval}` | `/skapi/services/historical/{exchange}/{scripcode}/{interval}` |

`master` and `historical` can be called without an account ID. In that mode, broker-router creates a client with an empty API key and calls the raw endpoint.

## Sharekhan Raw Client

`SharekhanRawClient` constructs:

- URLs from `base_url` and named route templates.
- Headers containing `api-key`, `Content-Type`, optional `access-token`, and optional `vendor-key`.
- Login URL query params: `api_key`, optional `vendor_key`, optional `state`.
- Optional per-account proxy URL composed from scheme, host, port, username, and password, then passed to `httpx.AsyncClient` for Sharekhan REST API requests.
- Access-token/profile payloads that match the Postman collection: `apiKey`, converted `FinalEncryptedToken` as `requestToken`, `state`, `versionId`, and optional `vendorkey`.

Order payloads are converted to JSON-ready values by stringifying `Decimal` values and dropping `None` fields.

Order response normalization checks these fields:

- Broker order ID: `orderId`, `order_id`, or `orderNo`.
- Status: `status`, `orderStatus`, or top-level `status`.
- Message: `message` or top-level `message`.

## WebSocket Stream Endpoints

| Method | Path | Description |
| --- | --- | --- |
| `POST` | `/sharekhan/ws/connect/{account_id}` | Starts a background Sharekhan WebSocket connection for the account. |
| `POST` | `/sharekhan/ws/subscribe/{account_id}` | Adds symbols to the in-memory subscription set. |
| `POST` | `/sharekhan/ws/unsubscribe/{account_id}` | Removes symbols from the in-memory subscription set. |
| `POST` | `/sharekhan/ws/disconnect/{account_id}` | Cancels and removes the background connection. |

`WsSubscription` request:

```json
{
  "symbols": ["2475", "2885"],
  "exchange": "NC"
}
```

Confirmed Sharekhan socket URL:

```text
{SHAREKHAN_WS_URL}?ACCESS_TOKEN={access_token}&API_KEY={api_key}
```

`SHAREKHAN_WS_URL` should remain the base socket URL:

```text
wss://stream.sharekhan.com/skstream/api/stream
```

Confirmed Sharekhan socket flow:

1. Connect with both `ACCESS_TOKEN` and `API_KEY`.
2. Send the module subscription frame:

```json
{
  "action": "subscribe",
  "key": ["feed", "ack"],
  "value": [""]
}
```

3. Wait through any initial `message: "connect"` frame, then wait for a `message: "subscribe"` response containing feed and ack success markers. The implementation accepts case and spacing variants such as `successFEED,successACK`, `successFeed,successAck`, `success Feed, success Ack`, and `success FEED,success ACK`.
4. Send feed subscription frames for market data. The Sharekhan instrument format is `{exchangeCode}{scripCode}`, for example `NC2885`.

```json
{
  "action": "feed",
  "key": ["ltp"],
  "value": ["NC2885"]
}
```

5. Send ack subscription frame for live order status:

```json
{
  "action": "ack",
  "key": [""],
  "value": ["CUSTOMER_ID"]
}
```

Supported feed keys from the supplied Sharekhan example:

| Key | Purpose |
| --- | --- |
| `ltp` | Last traded price and core quote fields. |
| `depth` | Market depth / bid-offer view. |
| `full` | Feed, depth, and bid/off combined. |

Current implementation status:

- The current code builds the connection URL as `{SHAREKHAN_WS_URL}?ACCESS_TOKEN={access_token}&API_KEY={api_key}`.
- Broker-router sends Sharekhan's module subscription frame after socket open.
- Broker-router waits through initial `connect` frames before evaluating module subscription readiness.
- Broker-router sends an ack subscription when the account has `customer_id` and module readiness is confirmed.
- If `/sharekhan/ws/connect/{account_id}` is called while an account socket is already connected, broker-router refreshes the stored access token, API key, customer id, and proxy metadata. If modules are already ready but ack has not been sent, it sends the order ack subscription on that existing socket.
- Broker-router sends feed frames for current subscriptions using values such as `NC2885`.
- Incoming messages are published to Redis channel `sharekhan:ticks` with a `type` field such as `subscribe`, `feed`, `ack`, or `raw`.
- Stream status exposes `last_sent_payload` and recent `sent_payloads`, including the outbound module `subscribe`, order `ack`, and feed frames.
- Stream errors are published to Redis channel `sharekhan:stream_errors`.
- Unsubscribe currently updates local subscription state only because the confirmed Sharekhan unsubscribe frame is not yet known.
- Feed and ack messages are typed on the same Redis channel; a future implementation may split order acknowledgements into `sharekhan:order_acks`.

Implementation target:

- Keep URL-encoded query params for `ACCESS_TOKEN` and `API_KEY`.
- Keep module subscription immediately after socket open.
- Replay module, feed, and ack subscriptions after reconnect.
- Convert API subscription requests from `{exchange: "NC", symbols: ["2885"]}` to Sharekhan values such as `NC2885`.
- Confirm the official unsubscribe frame and send it from `/sharekhan/ws/unsubscribe/{account_id}`.
- Consider a separate channel such as `sharekhan:order_acks` if consumers need independent routing.
- Avoid logging access tokens, API keys, customer ids, or full raw order acknowledgement payloads in production logs.

## Error Behavior

| Condition | Response |
| --- | --- |
| Account missing | `404 Broker account not found` |
| Missing request token | `400 Sharekhan request token is missing; complete account login first` |
| Missing access token | `400 Sharekhan access token is missing` |
| Invalid order action for endpoint | `422` |
| Stored credential cannot decrypt | `422 Re-save the account credentials with the current app secret` |
| Rate limit exceeded | `429` |
| Sharekhan HTTP error | Propagated by `httpx.raise_for_status()` |

## Security Notes

- Broker-router has no user-level auth. Keep it internal.
- It can decrypt all broker credentials reachable through the shared database URL.
- Proxy host, username, and password are encrypted at rest because they may contain sensitive network details.
- Production deployments should restrict network access so only the main API and worker can call broker-router.
- Keep `PAPER_TRADING_MODE=true` until live order placement has been explicitly approved.
