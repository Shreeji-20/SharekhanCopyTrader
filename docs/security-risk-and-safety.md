# Security, Risk, And Safety

This app can place real market orders when live mode is enabled. The default configuration is intentionally safer: `PAPER_TRADING_MODE=true` and `COPY_TRADING_DRY_RUN=true`.

## Credential Security

Broker account credentials and tokens are encrypted before storage:

- `api_key`
- `secret_key` (the Sharekhan Secure Key)
- `vendor_key`
- `proxy_host`
- `proxy_username`
- `proxy_password`
- `request_token`
- `access_token`
- `refresh_token`

Encryption implementation:

- AES-GCM from `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.
- 12-byte random nonce per encryption.
- Output is URL-safe base64 of `nonce + ciphertext`.
- Key is either a 32-byte base64-decoded `APP_SECRET_KEY` or SHA-256 of the configured string.

Response masking:

- `mask_secret` shows the first 4 and last 4 characters for long values.
- Short values are fully replaced by asterisks.
- API account responses return masked secrets and proxy passwords only.

Operational implication: `APP_SECRET_KEY` must be protected and backed up. If it changes without re-encrypting stored data, existing credentials and tokens cannot be decrypted. Account list responses mark such rows as `CREDENTIALS_LOCKED` so an operator can re-enter the API Key and Secure Key, then re-enter or clear optional vendor/proxy details, instead of the account list failing.

## Authentication And Authorization

### JWT

The main API signs JWT access tokens using:

- `JWT_SECRET`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`

The token subject is the user UUID.

Sharekhan login uses a random numeric `state` as a broker callback parameter. The API stores that state on the account before opening Sharekhan, so the public callback can identify the account without decrypting the request token. The callback endpoint saves the returned raw request token, then immediately asks broker-router to exchange it for Sharekhan access/profile details. Later account accordion views display only stored masked details.

### Passwords

Passwords are hashed with Passlib bcrypt.

### Role-Based Access

Current roles:

- `USER`
- `ADMIN`

`USER` access is scoped to the user's broker accounts and related copy groups, settings, orders, portfolio rows, and logs. `ADMIN` can access all rows through the implemented query scopes.

## Broker-Router Boundary

Broker-router does not validate user JWTs. It trusts callers that can reach it.

Required deployment controls:

- Keep broker-router private.
- Allow calls only from the main API and worker.
- Do not expose broker-router to the public internet.
- Keep database access private because broker-router can decrypt stored broker credentials.

When an account has proxy details, broker-router composes the proxy URL and uses it for that account's Sharekhan REST API calls. Use trusted proxy infrastructure only, because proxy operators can observe connection metadata and may affect order latency.

## Paper Trading Safety Switch

`PAPER_TRADING_MODE=true` causes broker-router order mutation endpoints to return simulated responses for:

- Place order.
- Modify order.
- Cancel order.

No live Sharekhan order is sent in this mode.

Important distinction:

- Paper mode short-circuits order mutation endpoints.
- Broker data endpoints and WebSocket connection still require valid access tokens.
- Live copy sessions also check `COPY_TRADING_DRY_RUN`; when it is true, copied child order payloads are stored but not submitted.

## Live Copy Safety Switch

`COPY_TRADING_DRY_RUN=true` causes `/live-copy` sessions to:

- Connect to the master Sharekhan WebSocket.
- Normalize executed ack events into `master_trade_events`.
- Build child Sharekhan order payloads.
- Store child attempts in `copied_trade_orders` with `SKIPPED` and a dry-run message.

No child order is sent to Sharekhan unless `COPY_TRADING_DRY_RUN=false`, `PAPER_TRADING_MODE=false`, and the session is started with `dry_run=false`.

## Risk Controls

The worker enforces per-target risk rules before sending copy orders.

### Account And Setting Controls

- Copy account must be active.
- Copy account must have a token according to the job payload.
- Copy setting must be enabled.

### Market-Hours Control

When `enforce_market_hours=true`, orders are allowed only:

- Monday through Friday.
- `09:15` to `15:30` Asia/Kolkata.

### Symbol Controls

- `blocked_symbols` always rejects matching symbols.
- `allowed_symbols` acts as an allow-list when non-empty.

### Side And Product Controls

- `allowed_transaction_types` filters sides such as `B` and `S`.
- `allowed_product_types` filters product types when non-empty.
- `product_type_map` can map master product type to copy product type.

### Quantity Controls

Supported sizing:

- Same quantity.
- Multiplier.
- Fixed quantity.
- Percent of copy account capital.

Additional caps:

- `max_qty`
- `max_order_value`

### Price Controls

Supported price modes:

- Same price.
- Market price encoded as `0`.
- Limit with slippage.

For slippage:

- Buy orders increase price by the slippage factor.
- Sell orders decrease price by the slippage factor.

## Duplicate Protection

The worker creates a deterministic idempotency key for each master order, copy account, and request type. It checks the database before sending and the database enforces uniqueness.

The live copy manager creates a session-scoped duplicate hash for each normalized master trade event. It also stores only one copied child order per master event and copier account, so selecting the same copier through multiple groups does not double-submit.

Duplicate behavior:

- Existing key means broker-router is not called.
- A skipped copy order is saved with reason `duplicate idempotency key`.

This protects against repeated queue messages for the same copy target.

## Audit Logging

The main API records audit logs for user-facing mutations and login:

- Registration.
- Login.
- Broker account create/update/delete.
- Broker request-token update.
- Broker token exchange/update.
- Broker stored profile view.
- Copy group create/update/delete.
- Copy group member add/remove.
- Copy setting update.
- Copy session start/pause/resume/stop/delete.

Current gaps:

- Worker copy order attempts are captured in `copy_orders`, not `audit_logs`.
- Broker-router raw broker calls are not audited in `audit_logs`.
- Most read actions are not audited; stored Sharekhan profile view is an explicit exception.

## High-Risk Actions

Treat these as high-risk operational actions:

- Setting `PAPER_TRADING_MODE=false`.
- Setting `COPY_TRADING_DRY_RUN=false`.
- Updating `APP_SECRET_KEY`.
- Changing `BROKER_ROUTER_URL`.
- Editing copy settings for live copy accounts.
- Disabling symbol/product filters.
- Increasing `max_qty` or `max_order_value`.
- Adding a new copy account to an active group.
- Running manual Redis jobs or live copy sessions against live accounts.

## Live Trading Checklist

Before enabling live trading:

1. Confirm all services are running the intended build.
2. Confirm `PAPER_TRADING_MODE=true` tests have produced expected paper orders.
3. Confirm `COPY_TRADING_DRY_RUN=true` live copy sessions produce expected would-send payloads.
4. Confirm every live account has valid Sharekhan tokens.
5. Confirm copy group membership exactly matches the intended copy plan.
6. Confirm every copy account has strict caps.
7. Confirm symbol and product filters are configured.
8. Confirm market-hours enforcement is enabled where applicable.
9. Confirm monitoring and logs are being watched.
10. Confirm the operator can manually stop the worker and `/live-copy` session quickly.
11. Change `PAPER_TRADING_MODE=false` and `COPY_TRADING_DRY_RUN=false` only for the intended environment.

## Threat And Failure Notes

| Risk | Current mitigation | Remaining gap |
| --- | --- | --- |
| Credential leak from database | AES-GCM encrypted columns | App secret compromise decrypts all credentials. |
| User accesses another user's account | Query scoping and ownership checks | Admin role has global access. |
| Public broker-router access | Intended private service | No service-level auth in code. |
| Duplicate queue jobs | Idempotency lookup and unique key | Concurrent duplicate inserts can still create DB unique errors. |
| Broker outage | Retry with exponential backoff | No dead-letter queue or alerting. |
| Bad job producer payload | Worker risk validation | Worker trusts account/settings payload freshness. |
| Live order mistake | Paper mode default and risk caps | No approval workflow in code. |
| Token expiry | Stores optional expiry | No automatic refresh workflow in code. |
| Lost app secret | Account rows show `CREDENTIALS_LOCKED` | Operator must re-enter broker credentials and optional vendor/proxy details, or restore the original key. |

## Recommended Hardening

- Add service-to-service auth for broker-router.
- Add admin bootstrap and explicit admin management.
- Add token refresh and token expiry alerts.
- Add dead-letter handling for failed worker jobs.
- Add structured audit for broker-router and worker actions.
- Add queue payload signing or load account/settings from database at processing time.
- Add alerting on failed copy order spikes and stream errors.
- Add a protected live-mode change procedure outside application code.
