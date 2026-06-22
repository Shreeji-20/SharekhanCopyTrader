# Main API

The main API lives in `apps/api`. It is a FastAPI service that exposes the user-facing backend contract and owns the primary SQLAlchemy ORM models.

## Runtime

| Item | Value |
| --- | --- |
| App entry | `apps/api/app/main.py` |
| ASGI server | `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Dockerfile | `apps/api/Dockerfile` |
| Public port in compose | `8000` |
| Database | Async SQLAlchemy using `DATABASE_URL` |
| Migrations | Alembic under `apps/api/alembic` |

## Core Modules

| File | Purpose |
| --- | --- |
| `app/main.py` | FastAPI app, CORS, health endpoint, router registration. |
| `app/models.py` | ORM entities, enums, relationships. |
| `app/schemas.py` | Pydantic request/response schemas and validation. |
| `app/dependencies.py` | Database dependency, bearer token decoding, current user loading, admin check helper. |
| `app/security.py` | Password hashing, JWT creation/decoding, secret masking. |
| `app/encryption.py` | AES-GCM encryption/decryption for credentials and tokens. |
| `app/audit.py` | Audit log helper. |
| `app/services/broker_router.py` | Internal HTTP client for broker-router login URL and token exchange. |
| `app/services/script_master.py` | Script Master normalization, database refresh, search data preparation, tick-size parsing, and missing-`scripCode` resolution for live copy. |
| `app/routers/users.py` | Admin-only complete user-record export/import with archive validation, conflict checks, and audit events. |

## Authentication

The API uses bearer JWTs.

1. `POST /auth/register` creates a user with a bcrypt password hash.
2. `POST /auth/login` verifies the password and returns an access token.
3. Authenticated routes use `OAuth2PasswordBearer(tokenUrl="/auth/login")`.
4. `get_current_user` decodes the JWT, loads the `User`, and rejects inactive or missing users.

JWT payload fields:

| Field | Meaning |
| --- | --- |
| `sub` | User UUID string. |
| `role` | User role value. |
| `exp` | Expiry timestamp. |

## Authorization

Most routes are user scoped:

- `ADMIN` can see all rows.
- `USER` can access only broker accounts owned by their `user_id`.
- Copy groups are scoped by the owning user of the master account.
- Copy settings are scoped by the owning user of the copy account.
- Logs are scoped to `audit_logs.user_id` for non-admin users.
- `/users/export` and `/users/import` require `ADMIN` and expose every stored user column, including password hashes.

## User Archive

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/users/export` | Export all `users` table columns in a versioned JSON archive with `Cache-Control: no-store`. Admin only. |
| `POST` | `/users/import` | Validate and upsert a version-1 archive by user UUID. Admin only. |

The archive preserves `id`, `email`, `password_hash`, `role`, `is_active`, `created_at`, and `updated_at`. Import creates missing UUIDs, fully updates changed UUIDs, counts identical rows, and does not delete users omitted from the file. Email/UUID conflicts reject the complete import. The current administrator cannot deactivate or demote their own record through import.

See [User Import And Export](user-import-export.md) for the JSON contract and credential-handling requirements.

## Endpoint Reference

### Health

| Method | Path | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/health` | No | Returns `{"status": "ok"}`. |

### Auth

| Method | Path | Auth | Request | Response |
| --- | --- | --- | --- | --- |
| `POST` | `/auth/register` | No | `UserCreate` | `UserRead` |
| `POST` | `/auth/login` | No | `LoginRequest` | `Token` |
| `GET` | `/auth/me` | Yes | None | `UserRead` |

Important validation:

- Emails are validated and lowercased.
- Passwords must be at least 10 characters.
- Duplicate registration returns `409`.
- Invalid login returns `401`.

### Accounts

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/accounts` | List accounts visible to the current user. |
| `POST` | `/accounts` | Create a Sharekhan broker account and encrypt credentials. |
| `GET` | `/accounts/{account_id}` | Read one account. |
| `PATCH` | `/accounts/{account_id}` | Update account metadata, active flag, account type, or credentials. |
| `DELETE` | `/accounts/{account_id}` | Delete an account. |
| `POST` | `/accounts/{account_id}/sharekhan/login-url` | Ask broker-router to generate a Sharekhan login URL with a random numeric `state`. |
| `POST` | `/accounts/sharekhan/callback` | Public Sharekhan redirect endpoint that saves the returned raw `request_token`, then immediately exchanges it for Sharekhan access-token/profile details. |
| `GET` | `/accounts/{account_id}/sharekhan/profile` | Return stored masked Sharekhan login/token details. This does not call Sharekhan's access-token endpoint. |
| `POST` | `/accounts/{account_id}/sharekhan/token` | Ask broker-router to exchange a request token and store broker tokens. |
| `POST` | `/accounts/{account_id}/sharekhan/orders/place` | Place a Sharekhan `NEW` order through broker-router. |
| `POST` | `/accounts/{account_id}/sharekhan/orders/modify` | Modify a Sharekhan order through broker-router. |
| `POST` | `/accounts/{account_id}/sharekhan/orders/cancel` | Cancel a Sharekhan order through broker-router. |
| `GET` | `/accounts/{account_id}/sharekhan/funds/{exchange}` | Fetch Sharekhan funds/limits for an exchange segment. |
| `GET` | `/accounts/{account_id}/sharekhan/reports` | Fetch Sharekhan order book/reports. |
| `GET` | `/accounts/{account_id}/sharekhan/trades` | Fetch Sharekhan trades/positions endpoint. |
| `GET` | `/accounts/{account_id}/sharekhan/orders/{exchange}/{order_id}` | Fetch Sharekhan order details/history. |
| `GET` | `/accounts/{account_id}/sharekhan/orders/{exchange}/{order_id}/trades` | Fetch trades generated by a Sharekhan order. |
| `GET` | `/accounts/{account_id}/sharekhan/holdings` | Fetch Sharekhan holdings. |
| `GET` | `/accounts/{account_id}/sharekhan/master/{exchange}` | Fetch Sharekhan scrip master data through a selected account. |
| `GET` | `/accounts/{account_id}/sharekhan/historical/{exchange}/{scripcode}/{interval}` | Fetch Sharekhan historical data through a selected account. |
| `POST` | `/accounts/{account_id}/sharekhan/ws/connect` | Connect the account's Sharekhan WebSocket stream. |
| `POST` | `/accounts/{account_id}/sharekhan/ws/subscribe` | Subscribe to Sharekhan feed symbols using `{exchange, symbols}`. |
| `POST` | `/accounts/{account_id}/sharekhan/ws/unsubscribe` | Remove local Sharekhan feed subscriptions. |
| `POST` | `/accounts/{account_id}/sharekhan/ws/disconnect` | Disconnect the account's Sharekhan WebSocket stream. |

Account create fields:

| Field | Required | Notes |
| --- | --- | --- |
| `account_name` | Yes | 1 to 120 chars. |
| `customer_id` | No | Optional Sharekhan customer ID. Normally filled automatically during callback token exchange. |
| `login_id` | No | Optional Sharekhan channel user/login ID. Normally filled automatically during callback token exchange. |
| `api_key` | Yes | Encrypted before storage. |
| `secret_key` | Yes | Sharekhan Secure Key. Encrypted before storage. |
| `vendor_key` | No | Optional vendor key. Encrypted when present. |
| `proxy_scheme` | No | Optional proxy scheme, `http` or `https`. |
| `proxy_host` | No | Optional proxy host. Required when any proxy detail is provided. Encrypted before storage. |
| `proxy_port` | No | Optional proxy port, 1 to 65535. Required when any proxy detail is provided. |
| `proxy_username` | No | Optional proxy ID/username. Encrypted before storage. |
| `proxy_password` | No | Optional proxy password. Requires `proxy_username` and is encrypted before storage. |
| `account_type` | Yes | `MASTER` or `COPY`. |

Returned account secrets are masked. The API never returns raw credentials or raw tokens.

Account read responses also include `credentials_readable`. When encrypted fields cannot be decrypted with the current `APP_SECRET_KEY`, the response still loads, masked secret fields show `UNREADABLE`, and `credentials_readable=false`. The frontend displays this as `CREDENTIALS_LOCKED`; re-enter the API Key and Secure Key, then re-enter or clear optional vendor/proxy details in the edit drawer to recover the account.

Sharekhan credential note:

- Mirae Asset Sharekhan issues an API Key and Secure Key for Trading API access.
- The app stores that Secure Key in the internal `secret_key` field name.
- Customer ID and channel user are not required during account creation. Broker-router stores them from Sharekhan's access-token response when present.
- Normal browser login uses `POST /accounts/{account_id}/sharekhan/login-url` followed by Sharekhan redirecting to `/sharekhan/callback`, which calls `POST /accounts/sharekhan/callback`.
- The callback saves the raw `request_token`, immediately asks broker-router to decrypt it, build `FinalEncryptedToken`, send `{apiKey, requestToken, state, versionId}` to Sharekhan's access-token endpoint, and store the returned `data.token` plus profile fields.
- After a successful token exchange, the API schedules Script Master warm-up for the exchanges returned by Sharekhan plus `SCRIPT_MASTER_PRELOAD_EXCHANGES`. Fresh PostgreSQL rows are loaded into the in-process index; stale or empty exchanges are refreshed through broker-router.
- Opening the account accordion only displays stored/masked account details; it does not re-run the Sharekhan access-token exchange.

### Script Master

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/script-master/search?query={text}&account_id={account_id}&limit={limit}` | Search normalized Script Master rows. With an account id, validates account access and returns account-specific added state. |
| `POST` | `/script-master/watchlist` | Add `{account_id, instrument_id}` to the authenticated user's account-specific watchlist. Duplicate natural keys return the existing row. |
| `GET` | `/script-master/watchlist?account_id={account_id}` | List the authenticated user's watchlist, optionally filtered to one owned account. |
| `DELETE` | `/script-master/watchlist/{item_id}` | Remove a watchlist item owned by the authenticated user. |
| `GET` | `/script-master/{exchange}/status` | Return cached row count and latest refresh timestamp for an exchange. |
| `POST` | `/script-master/{exchange}/refresh?account_id={account_id}` | Fetch Sharekhan Scrip Master data through a logged-in account and replace the normalized PostgreSQL cache for that exchange. |

Script Master cache details:

- Data is stored in `script_master_instruments`.
- Search is case-insensitive across trading symbol, symbol name, underlying, scrip code, and ISIN. Terms shorter than two characters return no results; the default limit is `50` and maximum is `100`.
- Normalized rows include lot size and tick size. `raw_payload_json` preserves additional provider fields.
- Refresh is exchange scoped and uses the existing broker-router `GET /sharekhan/master/{exchange}?account_id=...` path.
- The API keeps a per-process in-memory cache keyed by exchange for live-copy symbol resolution.
- Login warm-up loads normalized rows from PostgreSQL into memory immediately after account login. If an API process restarts before warm-up runs, the first lookup for an exchange still loads normalized rows from PostgreSQL once; subsequent lookups use the in-memory rows and indexes.
- Concurrent login warm-ups are coalesced by exchange. Multiple accounts logging in together do not download the same exchange repeatedly; waiting tasks reuse the first task's fresh `refreshed_at` result and memory index.
- The live copy engine uses cached Script Master rows on the WebSocket hot path. If an exchange cache has rows, those rows are used even when stale so order copying is not delayed by a refresh. If the exchange cache is empty, live copy may fetch it once through the selected master account.
- The default TTL is `24` hours.
- Manual refresh records `script_master.refresh` in audit logs and replaces or invalidates that API process's in-memory exchange cache.
- The memory cache is not shared across API instances; in multi-instance deployments, refresh each instance or restart/route refresh consistently if cache coherence is required.

Watchlist details:

- Rows are stored in `script_master_watchlist_items` and scoped by `user_id` plus `account_id`.
- Unique `(user_id, account_id, exchange, scrip_code)` prevents duplicate instruments for the same account.
- Watchlist rows store a JSON instrument snapshot because exchange refresh replaces Script Master cache row UUIDs.
- Reads prefer the current cache row joined by `(exchange, scrip_code)` and fall back to the snapshot when no current row exists.
- Add and remove operations emit `script_master.watchlist_add` and `script_master.watchlist_remove` audit events.
- Full request/response behavior is documented in [Script Master Search And Watchlist](script-master-search-and-watchlist.md).

Live-copy matching uses:

- Equity: `tradingSymbol` plus `exchange`/`segment`, refined by `ISIN` or `lotSize` when present.
- Derivatives: symbol/underlying, expiry, strike, option type, exchange/segment, and optional instrument type/lot size.
- Ambiguous matches never place orders.

### Copy Groups

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/copy-groups` | List copy groups visible to current user. |
| `POST` | `/copy-groups` | Create a group with a `MASTER` account. |
| `GET` | `/copy-groups/{group_id}` | Read a group. |
| `PATCH` | `/copy-groups/{group_id}` | Update name, active flag, or master account. |
| `DELETE` | `/copy-groups/{group_id}` | Delete a group. |
| `POST` | `/copy-groups/{group_id}/members` | Add a `COPY` account to a group and create group-scoped copy settings. Body may include `copy_setting`. |
| `PATCH` | `/copy-groups/{group_id}/members/{member_id}` | Enable/disable a member and update that member's group-scoped risk/copy settings. |
| `DELETE` | `/copy-groups/{group_id}/members/{member_id}` | Remove a group member. |

Validation:

- `master_account_id` must point to an account of type `MASTER`.
- `copy_account_id` must point to an account of type `COPY`.
- Duplicate copy account membership in the same group returns `409`.
- Copy settings are stored per `(copy_group_id, copy_account_id)`; editing one group member does not change the same account in another group.

Member risk/copy setting fields:

| Field | Notes |
| --- | --- |
| `is_enabled` | Enables/disables the copy setting separately from the member enabled flag. |
| `sizing_mode` | `SAME_QTY`, `MULTIPLIER`, `FIXED_QTY`, or `PERCENT_CAPITAL`. |
| `multiplier`, `fixed_qty`, `capital_percent` | Sizing inputs. `fixed_qty` is required when `sizing_mode=FIXED_QTY`. |
| `min_qty`, `max_qty` | Quantity bounds. Live copy skips when calculated quantity is outside the bounds. |
| `max_trades_per_day` | Per group/account placed-order limit. |
| `max_daily_loss` | Account loss guard based on stored positions PnL. |
| `max_order_value` | Maximum notional value for a child order. |
| `allowed_symbols`, `blocked_symbols` | Uppercased symbol filters. |
| `allowed_transaction_types` | Side filter; only `B` and `S` are valid. |
| `allowed_product_types`, `product_type_map` | Product allow-list and master-to-copy product mapping. |
| `price_mode`, `max_slippage_percent` | Price transformation controls. |
| `is_auto_squareoff_enabled` | Stored account/group setting for future square-off behavior. |

### Copy Settings

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/copy-settings/{copy_account_id}` | Read settings for a copy account in a required `copy_group_id`. |
| `PATCH` | `/copy-settings/{copy_account_id}` | Update or create settings for a copy account and group. |

Query:

| Parameter | Required | Notes |
| --- | --- | --- |
| `copy_group_id` | Required for read; required for patch unless body includes `copy_group_id` | Used to select the group-specific setting. |

The `/copy-settings` endpoint no longer falls back to the first settings row for a copy account. This prevents accidental global-looking edits when an account belongs to multiple copy groups.
It also verifies that the current user can access the group and that the copy account is an actual member of that group.

Patch body supports sizing, filters, product mapping, price mode, slippage, square-off flag, and enabled flag.

### Portfolio

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/positions` | List position snapshots. |
| `GET` | `/holdings` | List holding snapshots. |
| `GET` | `/trades` | List trade snapshots. |

Positions and trades support `search`, `limit`, and `offset`. Holdings support `limit` and `offset`.

### Logs

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/logs` | List audit logs visible to current user. |

Query parameters:

| Parameter | Default | Notes |
| --- | --- | --- |
| `action` | None | Case-insensitive partial match. |
| `limit` | `100` | Max `500`. |
| `offset` | `0` | Must be non-negative. |

### Dashboard

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/dashboard/metrics` | Aggregated dashboard metrics. |

Returned metrics:

- `active_copy_accounts`
- `open_positions`
- `total_pnl`
- `broker_connection_status`

`broker_connection_status` is:

- `CONNECTED` when every active account has an access token.
- `DEGRADED` when some active accounts have access tokens.
- `DISCONNECTED` when there are no active accounts or none have tokens.

### Live WebSocket

| Method | Path | Description |
| --- | --- | --- |
| WebSocket | `/ws/live` | Accepts a socket and sends heartbeat JSON every 5 seconds. |

Current payload:

```json
{"type": "heartbeat", "status": "ok"}
```

This endpoint is not yet connected to Redis tick streams or order events.

## Sharekhan Order Schema

`SharekhanOrderPayload` exists in the API schema module and broker-router schema module. It validates normalized Sharekhan order fields:

- `transactionType` must be `B` or `S`.
- `requestType` must be `NEW`, `MODIFY`, or `CANCEL`.
- For `NEW`, fields like `customerId`, `scripCode`, `tradingSymbol`, `exchange`, `transactionType`, `quantity`, `price`, `channelUser`, and `productType` are required.
- For `MODIFY` and `CANCEL`, `orderId` is required.
- `tradingSymbol`, `exchange`, and `productType` are stripped and uppercased.

## Audit Events

The API records audit logs for:

- `account.register`
- `auth.login`
- `broker_account.create`
- `broker_account.update`
- `broker_account.delete`
- `broker_account.request_token_update`
- `broker_account.profile_view`
- `broker_account.token_update`
- `script_master.refresh`
- `copy_group.create`
- `copy_group.update`
- `copy_group.delete`
- `copy_group.member_add`
- `copy_group.member_remove`
- `copy_setting.update`

## Example API Flow

Register:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com","password":"change-this-password"}'
```

Login:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com","password":"change-this-password"}'
```

Create an account:

```bash
curl -X POST http://localhost:8000/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "account_name": "Primary Account",
    "api_key": "SHAREKHAN_API_KEY",
    "secret_key": "SHAREKHAN_SECURE_KEY",
    "vendor_key": null,
    "proxy_scheme": "http",
    "proxy_host": "proxy-host",
    "proxy_port": 8080,
    "proxy_username": "user",
    "proxy_password": "pass",
    "account_type": "MASTER"
  }'
```

Generate Sharekhan login URL:

```bash
curl -X POST http://localhost:8000/accounts/$ACCOUNT_ID/sharekhan/login-url \
  -H "Authorization: Bearer $TOKEN"
```

The response includes `login_url` and a random numeric `state`. The same state is embedded in the login URL and stored on the account so the public callback can identify the account even if browser tab storage is unavailable.

Callback request-token save and automatic access-token exchange:

```bash
curl -X POST http://localhost:8000/accounts/sharekhan/callback \
  -H "Content-Type: application/json" \
  -d '{"state":"STATE_FROM_SHAREKHAN","request_token":"REQUEST_TOKEN_FROM_SHAREKHAN"}'
```

View stored Sharekhan login/token details:

```bash
curl http://localhost:8000/accounts/$ACCOUNT_ID/sharekhan/profile \
  -H "Authorization: Bearer $TOKEN"
```

Authenticated manual token exchange:

```bash
curl -X POST http://localhost:8000/accounts/$ACCOUNT_ID/sharekhan/token \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"request_token":"REQUEST_TOKEN_FROM_SHAREKHAN"}'
```

The stored profile endpoint is useful for checking masked token/customer status, but it does not call Sharekhan. The manual token endpoint is retained for internal/admin-style tooling; the normal web callback already performs token exchange after saving the raw request token.

On successful profile/token exchange, the API response includes masked tokens and the returned `customer_id`, `login_id`, full name, broker, exchanges, and expiry values when available.

## Known Notes

- There is no admin creation endpoint. Users register as `USER` by default unless changed directly in the database or future admin tooling.
- Broker-router calls made by the main API use `httpx.AsyncClient` and raise upstream HTTP errors directly.
- Dashboard metrics depend on database rows that are not fully populated by current ingestion code.
- CORS defaults to `["http://localhost:3000"]` from settings.
