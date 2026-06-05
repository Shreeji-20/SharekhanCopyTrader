# Testing And Operations

This document covers how to verify the app and operate it safely.

## Test Suites

| Service | Test path | Coverage |
| --- | --- | --- |
| API | `apps/api/tests/test_security_and_schemas.py`, `apps/api/tests/test_live_copy.py` | Secret masking, encryption round trip, unreadable credential recovery response, stored Sharekhan profile display, proxy validation, Sharekhan order payload validation, live copy ack normalization, Script Master symbol matching, missing-`scripCode` live-copy enrichment, and child order payload building. |
| Broker-router | `apps/broker-router/tests/test_sharekhan_client.py` | Raw route URL construction, Sharekhan header/login URL construction, proxy composition, unreadable credential errors, raw request-token access payload, Sharekhan module subscription readiness parsing, connect-before-subscribe handling, and outbound order ack subscription payloads. |
| Worker | `apps/worker/tests/test_risk_engine.py` | Quantity sizing, risk rejection, idempotency key stability, duplicate skip behavior, retry behavior. |

## Running Tests In Docker

```bash
docker compose run --rm api python -m pytest
docker compose run --rm broker-router python -m pytest
docker compose run --rm worker python -m pytest
```

These commands build/run service containers with their Python dependencies installed.

## Running Tests Locally

If running outside Docker, create separate Python environments or install each service's `requirements.txt`, then run pytest from the service directory.

API:

```bash
cd apps/api
python -m pytest
```

Broker-router:

```bash
cd apps/broker-router
python -m pytest
```

Worker:

```bash
cd apps/worker
python -m pytest
```

## Health Checks

Main API:

```bash
curl http://localhost:8000/health
```

Expected:

```json
{"status":"ok"}
```

Broker-router:

```bash
curl http://localhost:8001/health
```

Expected:

```json
{"status":"ok","paper_trading_mode":true}
```

Frontend:

```bash
curl http://localhost:3000
```

Expected: Next.js serves the app and redirects to dashboard in the browser.

## Manual Smoke Test

1. Start services:

```bash
docker compose up --build
```

2. Run migrations if `RUN_MIGRATIONS=false`; otherwise the API container applies them on startup:

```bash
docker compose exec api alembic upgrade head
```

3. Register a user:

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com","password":"change-this-password"}'
```

4. Login and store the returned token:

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com","password":"change-this-password"}'
```

5. Create a master account and one copy account through the API or `/accounts/new`.

6. Generate a Sharekhan login URL:

```bash
curl -X POST http://localhost:8000/accounts/$ACCOUNT_ID/sharekhan/login-url \
  -H "Authorization: Bearer $TOKEN"
```

7. Confirm the returned login URL contains a numeric `state`, then complete Sharekhan login through that URL. Sharekhan should redirect to `http://localhost:3000/sharekhan/callback` with `state` and `request_token`.

8. Confirm the callback saves the request token and automatically stores the Sharekhan access token/profile identity. Open the account accordion only to view stored masked details.

9. Confirm broker-router health reports paper mode enabled.

10. Create a copy group and add the copy account.

11. Patch copy settings with low `max_qty` and `max_order_value`.

12. If testing worker order execution, ensure a matching `master_orders` row exists before enqueueing a copy job.

13. If testing live copy, keep `COPY_TRADING_DRY_RUN=true`, open `/live-copy`, select the master and copy group, start a dry-run session, then inspect captured master events and copied order attempts.

14. If Sharekhan ack messages are missing `scripCode`, refresh Script Master before live testing:

```bash
curl -X POST "http://localhost:8000/script-master/NC/refresh?account_id=$MASTER_ACCOUNT_ID" \
  -H "Authorization: Bearer $TOKEN"
```

Then check cache status:

```bash
curl http://localhost:8000/script-master/NC/status \
  -H "Authorization: Bearer $TOKEN"
```

## Worker Smoke Test Notes

The worker consumes jobs from Redis list `copy_jobs`. This repository does not include the job producer, so manual testing requires pushing a JSON job yourself.

Preconditions:

- Services are running.
- Migrations have been applied.
- `master_orders` contains a row whose `id` matches the job's `master_order.id`.
- Target account IDs in the job are valid copy account IDs.
- In paper mode, broker-router will simulate order placement.

High-level Redis command:

```bash
docker compose exec redis redis-cli LPUSH copy_jobs '<json job payload>'
```

Use the job payload shape documented in [Copy Worker](copy-worker.md). Keep quantities small and `PAPER_TRADING_MODE=true`.

## Live Copy Smoke Test Notes

The live copy manager consumes Sharekhan ack messages from Redis channel `sharekhan:ticks`. Use the smoke script only after the API, broker-router, Redis, and database are running and the selected master account is logged in.

PowerShell:

```powershell
$env:SMOKE_JWT="app-jwt"
$env:SMOKE_MASTER_ACCOUNT_ID="master-account-uuid"
$env:SMOKE_COPY_GROUP_IDS="copy-group-uuid"
$env:SMOKE_START_COPY_SESSION="true"
python tests/live_copy_smoke.py
```

The script validates selected groups, starts a dry-run session, checks event/order endpoints, and stops the session.

## Operational Checks

### API

- `/health` returns ok.
- `/auth/login` returns a token for known users.
- `/dashboard/metrics` works with a bearer token.
- Account responses mask secrets.
- Account responses load even when a row has unreadable encrypted fields, with `credentials_readable=false`.
- Audit logs are created for mutations.

### Broker-Router

- `/health` returns expected paper mode value.
- Login URL generation works for accounts with encrypted credentials.
- Callback/manual token exchange stores masked tokens and updates `last_connected_at`.
- WebSocket connect waits through initial Sharekhan `connect` frames, confirms module subscription readiness, and sends the outbound order ack subscription when `customer_id` is present.
- Paper order placement returns `paper_trading=true`.
- Live broker calls are blocked when access token is missing.

### Worker

- Process is running.
- Redis connection is healthy.
- Queue depth for `copy_jobs` is not growing unexpectedly.
- `copy_orders` rows are inserted for consumed jobs.
- Failed/skipped orders have useful `error_message` values.

### Web

- Login page can store token.
- Dashboard loads live metrics and empty states.
- Account creation, listing, editing, and deletion call the API successfully.
- Item login and central selected/all login generate Sharekhan login URLs.
- Sharekhan callback saves the raw request token and exchanges it through broker-router with `POST /accounts/sharekhan/callback`.
- Opening an account accordion displays stored masked Sharekhan details without calling the access-token endpoint again.
- Data tables render live API rows or empty states without demo data.
- Copy Groups page creates groups and manages members.
- Live Copy page starts dry-run sessions, pauses/resumes/stops/deletes sessions, displays master events plus copied order attempts, and shows stream diagnostics with recent sent/received WebSocket frames.
- Missing `scripCode` events are enriched through Script Master when a unique match exists. The master event raw payload includes `script_master_resolution`.

## Troubleshooting

| Symptom | Likely cause | Check |
| --- | --- | --- |
| API cannot start | Database URL or dependency issue | API logs, `DATABASE_URL`, Postgres health. |
| `alembic upgrade head` fails | DB not reachable or migration import issue | Run inside API container after Postgres health check. |
| Login fails | Wrong credentials, inactive user, JWT secret mismatch after restart | User row, password, `JWT_SECRET`. |
| Account secrets cannot decrypt | `APP_SECRET_KEY` changed | Restore original key or re-encrypt data. |
| Account shows `CREDENTIALS_LOCKED` | Stored encrypted fields cannot decrypt with active `APP_SECRET_KEY` | Edit the account, re-enter API Key and Secure Key, re-enter or clear optional vendor/proxy details, save, then run Sharekhan login again. |
| Accounts page says accounts could not be loaded | API request failed; older builds crashed on unreadable encrypted fields | Check API logs and rebuild/restart API/web with the credential recovery fix. |
| Sharekhan callback says sign in required | Older callback build used the authenticated token endpoint | Rebuild/restart API/web; start a fresh account login URL from Accounts. |
| Sharekhan callback says account could not be identified | Browser tab lost pending account id, or callback was opened directly | Start login again from the Accounts page for that specific account. |
| Broker-router says request token missing | Callback has not saved a Sharekhan request token for the account | Check `broker_accounts.request_token`; run account login again. |
| Broker-router says access token missing | Callback token exchange failed or has not run for the account | Run account login again, then check the callback response, `broker_accounts.access_token`, and broker-router logs. |
| Live Copy modules stay pending | Sharekhan module subscription did not return a successful `message=subscribe` response, or the running broker-router is stale | Start a fresh session after rebuilding/restarting broker-router; inspect Stream Status `recent_messages` for `connect` then `subscribe` success. |
| Ack subscribe stays pending | Missing `customer_id`, modules not ready, or an older socket was reused before ack was sent | Confirm `Customer: true`, `Modules: READY`, then inspect Stream Status `sent_payloads` for `{"action":"ack","key":[""],"value":["CUSTOMER_ID"]}`. Reconnect/start a fresh session if absent. |
| Live copy skips with `scripCode missing and could not be resolved` | WebSocket ack omitted `scripCode` and no unique Script Master row matched | Refresh `/script-master/{exchange}/refresh`, inspect `script_master_resolution` in the master event raw payload, and verify symbol/exchange/expiry/strike/option fields are present. |
| Live copy skips with `multiple Script Master matches found` | More than one Script Master row matched the event | Do not force placement. Refine incoming event fields or copy settings; inspect the candidate snapshots stored in `script_master_resolution.candidates`. |
| Script Master cache is empty | Master endpoint returned no parseable rows or refresh has not run | Call the refresh endpoint with a logged-in account and check API logs for `script_master.fetch_started`, `script_master.fetch_completed`, or `script_master.fetch_empty`. |
| Paper order unexpectedly live | `PAPER_TRADING_MODE=false` in broker-router environment | Check `/health` on broker-router. |
| Live copy order unexpectedly live | `COPY_TRADING_DRY_RUN=false`, `PAPER_TRADING_MODE=false`, and session `dry_run=false` | Re-enable safety flags and stop the session from `/live-copy`. |
| Worker inserts fail | Missing master order foreign key | Ensure `master_orders.id` exists before job. |
| Worker skips due to market closed | Market-hours enforcement enabled | Set `enforce_market_hours=false` only for controlled tests. |
| Duplicate skips | Same master/account/request type already processed | Inspect `copy_orders.idempotency_key`. |
| Web API calls fail | Missing token or wrong `NEXT_PUBLIC_API_URL` | Browser storage, network tab, API CORS settings. |
| Web tables are empty | No persisted records exist yet | Create accounts/orders/log-producing actions, then refresh the relevant screen. |

## Database Inspection Queries

Recent audit logs:

```sql
select action, entity_type, entity_id, created_at
from audit_logs
order by created_at desc
limit 20;
```

Recent copy orders:

```sql
select status, broker_order_id, calculated_quantity, error_message, retry_count, created_at
from copy_orders
order by created_at desc
limit 20;
```

Recent live copy sessions and copied orders:

```sql
select status, dry_run, master_account_id, started_at, stopped_at, last_error
from copy_sessions
order by created_at desc
limit 20;

select status, child_order_id, error_message, created_at
from copied_trade_orders
order by created_at desc
limit 20;
```

Script Master cache status:

```sql
select exchange, count(*) as rows, max(refreshed_at) as refreshed_at
from script_master_instruments
group by exchange
order by exchange;
```

Accounts with token status:

```sql
select account_name, account_type, is_active, access_token is not null as has_token, last_connected_at
from broker_accounts
order by created_at desc;
```

## Monitoring Recommendations

Track:

- API request errors and latency.
- Broker-router `429` responses.
- Broker-router Sharekhan HTTP errors.
- Worker process uptime.
- Worker retry and failure counts.
- Redis `copy_jobs` queue length.
- Redis stream error messages on `sharekhan:stream_errors`.
- Database connection usage.
- Copy order `FAILED` and `SKIPPED` rates.
- Live copy session status and `copied_trade_orders` `FAILED`/`SKIPPED` rates.

Suggested alerts:

- Worker down for more than 1 minute during trading hours.
- Any live-mode broker order failure spike.
- Queue depth increasing continuously.
- Broker-router health failure.
- Token expiry approaching for active accounts.
- `PAPER_TRADING_MODE` changed in production.
- `COPY_TRADING_DRY_RUN` changed in production.

## Release Checklist

1. Run API, broker-router, and worker tests.
2. Build the web app.
3. Run migrations in staging.
4. Verify paper order placement.
5. Verify account credential masking.
6. Review environment variables.
7. Confirm broker-router is private.
8. Confirm monitoring and rollback path.
9. Deploy.
10. Watch logs and copy order outcomes during the first market window.
