# Live Copy Trading

Live copy trading is implemented as a DRY_RUN-first workflow that listens to Sharekhan WebSocket order acknowledgements for a master account and records/copies executed trade events to selected copy groups.

## Safety Defaults

Real Sharekhan orders are blocked unless both global safety flags are deliberately disabled and the session is started with `dry_run: false`.

Required defaults:

```env
PAPER_TRADING_MODE=true
COPY_TRADING_DRY_RUN=true
```

When dry-run is active, the API still normalizes master trade events, builds the exact child order payloads, and stores rows in `copied_trade_orders`, but it does not call Sharekhan order placement.

## Data Model

New tables:

| Table | Purpose |
| --- | --- |
| `copy_sessions` | Tracks a live copy run for one master account and selected group ids. |
| `master_trade_events` | Stores normalized executed master trade events from Sharekhan ack messages. |
| `copied_trade_orders` | Stores each child order payload, dry-run result, Sharekhan response, or skip/failure reason. |
| `script_master_instruments` | Stores normalized Sharekhan Scrip Master rows used to resolve missing `scripCode` values from WebSocket order acks. |

Existing tables reused:

| Table | Purpose |
| --- | --- |
| `copy_groups` | Groups a master account with one or more copy accounts. |
| `copy_group_members` | Enables/disables copy account membership in a group. |
| `copy_settings` | Per copy account/group sizing, price mode, symbol filters, product filters, and limits. |

## Event Source

The main API starts a broker-router WebSocket connection for the selected master account:

```http
POST /accounts/{master_account_id}/sharekhan/ws/connect
```

Broker-router connects to Sharekhan:

```text
wss://stream.sharekhan.com/skstream/api/stream?ACCESS_TOKEN={{accessToken}}&API_KEY={{apiKey}}
```

It subscribes to modules and order acks, then publishes incoming messages to Redis channel:

```text
sharekhan:ticks
```

The live copy manager consumes that channel and filters messages by the master account id in the active session.

Sharekhan may send an initial successful `connect` frame before the module subscription acknowledgement:

```json
{
  "status": 100,
  "message": "connect",
  "data": "Connected session-id"
}
```

Broker-router waits through this connection frame and only treats a `message: "subscribe"` response containing feed and ack success markers as module readiness. If the socket is already connected and a later connect request arrives, broker-router refreshes the connection metadata and sends the ack subscription when modules are ready but order ack subscription has not yet been sent.

Ack subscription frame sent by broker-router after module readiness:

```json
{
  "action": "ack",
  "key": [""],
  "value": ["{{customerId}}"]
}
```

## Stream Diagnostics

Broker-router exposes stream status:

```http
GET /sharekhan/ws/status/{account_id}
```

Main API proxies that status through:

```http
GET /accounts/{account_id}/sharekhan/ws/status
GET /copy-sessions/{session_id}/stream-status
```

Important fields:

| Field | Meaning |
| --- | --- |
| `is_connected` | WebSocket is currently open. |
| `module_ready` | Sharekhan returned successful feed+ack module subscription. Detection tolerates case and spacing variants such as `successFEED/successACK`, `successFeed/successAck`, `success Feed/success Ack`, and `success FEED/success ACK`. |
| `ack_subscription_sent` | Broker-router sent the exact ack subscription frame with the account `customerId`. |
| `ack_messages_received` | Number of ack-shaped messages received from Sharekhan. |
| `last_sent_payload` | Most recent outbound WebSocket frame sent by broker-router. |
| `sent_payloads` | Recent outbound frames, including module `subscribe`, order `ack`, and feed subscriptions. Use this to confirm the order-streaming request was sent. |
| `recent_messages` | Last stream messages/status events kept in memory for operator diagnostics. |

If `module_ready=false`, ack subscription is blocked because Sharekhan did not confirm module readiness. If `ack_subscription_sent=false` with `customer_id_present=false`, complete account login again so the callback saves the access token and `customerId`. If modules are ready and customer is present but ack remains pending, reconnect or start a fresh session and inspect `sent_payloads`; a correct order-streaming subscription appears as `{"action":"ack","key":[""],"value":["CUSTOMER_ID"]}`.

## Ack Normalization Rules

Only order ack payloads with executed quantity are copied.

Ignored:

- `NewOrderConfirmation` and other acks where `TradeQty` is `0`.
- Payloads without ack identity fields like `SharekhanOrderID`, `ExchangeOrderID`, `AckState`, or `TradeID`.
- Payloads missing required trade basics: symbol, side, exchange, or positive quantity.

Normalized master event fields:

| Source field | Stored field |
| --- | --- |
| `TradeID` | `external_trade_id` |
| `SharekhanOrderID` / `ExchangeOrderID` | `external_order_id` |
| `TradingSymbol` | `symbol` |
| `Exchange` | `exchange` |
| `BuySellString` | `side` |
| `TradeQty` | `quantity` |
| `TradePrice` fallback `OrderPrice` | `price` |
| `OrderType` | `order_type` |
| `ProductType` fallback `INVESTMENT` | `product_type` |
| `ScripCode` / `ScripToken` / `Token` | `scrip_code` when present |
| `SegmentCode` / `Segment` | `segment` |
| `InstrumentType` / `InsType` | `instrument_type` |
| `OptionType` / `CPType` | `option_type` |
| `StrikePrice` / `Strike` | `strike_price` |
| `Expiry` / `ExpiryDate` | `expiry` |
| `LotSize` / `MarketLot` | `lot_size` |
| `ISIN` / `isinCode` | `isin` |
| Full ack envelope | `raw_payload_json` |

Duplicate protection uses a session-scoped hash of trade/order id, symbol, side, quantity, price, and event time.

## Scrip Code Resolution

Sharekhan WebSocket order acknowledgements do not always include `scripCode`. The live copy engine no longer skips these events immediately. It now resolves missing codes through cached Scrip Master data before building child orders.

Resolution flow:

```text
Master WebSocket ack
-> normalize event
-> use event.scripCode if present
-> otherwise use cached Script Master rows for the event exchange
-> match the instrument
-> inject resolved scripCode into the normalized event
-> build child order payloads
```

Cache behavior:

- Script Master rows are stored in PostgreSQL table `script_master_instruments`.
- The cache is exchange scoped, for example `NC` or `NF`.
- The default cache TTL is 24 hours through `SCRIPT_MASTER_CACHE_TTL_HOURS=24`.
- The API also keeps an in-process per-exchange memory cache of normalized Script Master rows and lookup indexes.
- After a successful Sharekhan login or manual token exchange, the API schedules a Script Master preload for the exchanges returned by the broker profile plus `SCRIPT_MASTER_PRELOAD_EXCHANGES`.
- Login preload uses the same TTL rules as normal cache loading: fresh PostgreSQL rows are loaded into memory, while stale or empty exchanges are refreshed through broker-router and then written to PostgreSQL plus memory.
- Script Master refresh is coalesced per exchange inside each API process. If 10 accounts log in at the same time and all ask to warm `NC`, the first task performs the TTL/`refreshed_at` check and broker download; the waiting tasks reuse the updated in-memory cache instead of downloading the same exchange again.
- Empty refresh attempts are also remembered in memory for the TTL window, so a temporary empty Script Master response returns `CACHE_EMPTY` without repeatedly calling Sharekhan on every login or live lookup.
- If an API process starts without a recent login preload, the first missing-`scripCode` lookup for an exchange loads that exchange from PostgreSQL once and stores it in memory.
- Subsequent lookups for the same exchange resolve against memory instead of running Postgres status/lookup queries.
- The in-memory cache has an identity dictionary keyed by exchange/segment plus trading symbol, underlying symbol, symbol name, and ISIN. Normal live-copy lookup is an O(1) dictionary hit to get the candidate set, followed by safety validation for expiry, strike, CE/PE, lot size, and ambiguity.
- Live copy uses stale-but-present exchange cache rows during WebSocket event handling so a Script Master refresh does not delay copying.
- If the exchange cache is empty, live copy may fetch it through the master account; operators should manually refresh active exchanges before live market use.
- Manual refresh is available through `POST /script-master/{exchange}/refresh?account_id={account_id}`.
- The memory cache is per API process. In multi-instance deployments each API instance has its own cache, and Script Master refresh invalidates/replaces only the cache in the instance that handled the refresh request.

Matching rules:

| Event type | Match fields |
| --- | --- |
| Event already has `scripCode` | Use it directly. Script Master is not called. |
| Equity/cash | `tradingSymbol` plus `exchange` or `segment`; `ISIN` and `lotSize` refine the match when present. |
| Derivatives | `tradingSymbol`/underlying plus `exchange` or `segment`, `expiry`, `strikePrice`, `optionType`, and optional `instrumentType`/`lotSize`. |

Safety rules:

- If one unique `scripCode` is found, the event gets `script_master_resolution.status=RESOLVED` and child order placement continues.
- If no record matches, child orders are skipped with `scripCode missing and could not be resolved...`.
- If multiple different `scripCode` values match, child orders are skipped with `multiple Script Master matches found...`.
- The engine never places an order from an ambiguous Script Master match.

The master event `raw_payload_json` stores `script_master_resolution` with the resolution status, message, candidate snapshots, and whether a cache refresh happened.

## Live Copy Latency

The WebSocket copy path is instrumented with structured logs and stored timing data in `master_trade_events.raw_payload_json.live_copy_timing_ms`.

Recorded timings include:

| Timing | Meaning |
| --- | --- |
| `parse_ms` | Time spent parsing the Redis/WebSocket payload into a normalized trade event. |
| `duplicate_lookup_ms` | Session-scoped duplicate-event lookup. |
| `scrip_code_resolution_ms` | Script Master lookup/enrichment time when `scripCode` is missing. |
| `target_load_ms` | Active copy group/member/account/settings load time. |
| `target_cache_hit` | `1` when live copy used the in-memory active-target cache, `0` when it reloaded from PostgreSQL. |
| `risk_lookup_ms` | Bulk lookup for per-group/account trade counts and account loss guard data. |
| `order_dispatch_ms` | Time spent preparing eligible child payloads and dispatching broker order calls. |
| `copier_target_count` | Number of deduped eligible target memberships considered. |
| `prepared_order_count` | Number of copier orders that passed risk/credential/dry-run checks and were sent to broker-router. |
| `max_dispatch_gap_ms` | Largest gap between copier order dispatch start offsets inside the batch. This should be near-zero unless dispatch throttling is configured. |
| `total_master_to_copier_ms` | End-to-end time from WebSocket message receipt to copied-order rows being ready for commit. |

Target loading behavior:

- Active selected copy groups, members, copy accounts, and `copy_settings` are cached per session for 15 seconds.
- Session start/resume preloads the target cache.
- Member/settings/group mutations invalidate cached targets for the affected master account.
- Live copy prepares and validates all copier payloads first, then dispatches only the prepared broker order calls.
- Copier placements are dispatched concurrently with `asyncio.gather(..., return_exceptions=True)`, so one slow or failed copy account does not delay dispatch start for other accounts.
- A shared broker-router HTTP client is used for each batch, avoiding per-copier API client setup.
- `LIVE_COPY_ORDER_DISPATCH_CONCURRENCY=0` means unlimited concurrent dispatch. Set it to a positive number only when broker/API throttling is required; this intentionally spaces dispatch starts and is logged as `broker_throttle_active=true`.
- If the same copy account appears in multiple selected groups, the existing safety dedupe keeps the first group by group creation order and logs `live_copy.duplicate_copier_skipped`.

## Child Order Payload

For every enabled copy account in the selected groups, the engine builds the documented Sharekhan order body:

```json
{
  "customerId": "COPY_CUSTOMER_ID",
  "scripCode": 2475,
  "tradingSymbol": "ONGC",
  "exchange": "NC",
  "transactionType": "B",
  "quantity": 1,
  "disclosedQty": 0,
  "price": "93.10",
  "triggerPrice": "0.00",
  "rmsCode": "ANY",
  "afterHour": "N",
  "orderType": "NORMAL",
  "channelUser": "COPY_LOGIN_ID",
  "validity": "GFD",
  "requestType": "NEW",
  "productType": "INVESTMENT"
}
```

The engine skips the child order when:

- Copy account is inactive.
- Required API key, secret key, customer id, login id, or access token is missing.
- Copy settings are disabled.
- Symbol, transaction type, or product type is blocked by settings.
- Calculated quantity is zero.
- Calculated quantity is below `min_qty`.
- Calculated quantity exceeds `max_qty`.
- Calculated order value exceeds `max_order_value`.
- `max_trades_per_day` has already been reached for that copy account in that group.
- `max_daily_loss` has already been reached for that copy account based on stored positions PnL.
- The master WebSocket event does not include `scripCode` and Script Master resolution fails.
- Multiple Script Master rows match the same event, so placing the order would be ambiguous.

## API Endpoints

Copy group validation:

```http
POST /copy-groups/validate
```

Body:

```json
{
  "master_account_id": "uuid",
  "copy_group_ids": ["uuid"]
}
```

Session lifecycle:

```http
POST /copy-sessions/start
POST /copy-sessions/{session_id}/pause
POST /copy-sessions/{session_id}/resume
POST /copy-sessions/{session_id}/stop
DELETE /copy-sessions/{session_id}
GET  /copy-sessions
GET  /copy-sessions/{session_id}
GET  /copy-sessions/{session_id}/events
GET  /copy-sessions/{session_id}/copied-orders
```

Script Master cache:

```http
GET  /script-master/{exchange}/status
POST /script-master/{exchange}/refresh?account_id={logged_in_account_id}
```

The refresh endpoint fetches Sharekhan `/skapi/services/master/{exchange}` through the selected account, normalizes rows, replaces the cached rows for that exchange, and records `script_master.refresh` in audit logs.

Deleting a copy session stops its listener, disconnects the master stream if that session was active, and removes captured events/orders through database cascade.

Start body:

```json
{
  "master_account_id": "uuid",
  "copy_group_ids": ["uuid"],
  "dry_run": true,
  "allow_duplicate_copiers": false
}
```

## Frontend

Screens:

| Route | Purpose |
| --- | --- |
| `/copy-groups` | Create, enable/disable, delete, and open copy groups. |
| `/copy-groups/{id}` | Manage group members, edit per-member risk/copy settings, and view preflight warnings. |
| `/live-copy` | Start dry-run/live sessions, pause/resume/stop, and inspect events/copied order attempts. |

The `/live-copy` Stream Status panel shows connection/module/ack state, message counts, the most recent sent payload, recent sent frames, and recent received frames. This panel is the first place to confirm that the outbound order-streaming `ack` request was sent after module readiness.

## Smoke Test

Dry-run session smoke:

```powershell
$env:SMOKE_JWT="app-jwt"
$env:SMOKE_MASTER_ACCOUNT_ID="master-account-uuid"
$env:SMOKE_COPY_GROUP_IDS="copy-group-uuid"
$env:SMOKE_START_COPY_SESSION="true"
python tests/live_copy_smoke.py
```

The script validates selected groups, starts a dry-run session, reads events/copied orders, and stops the session.
