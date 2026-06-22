# Configuration And Deployment

This app is designed to run locally through Docker Compose. Production deployment should preserve the same service boundaries while strengthening secret management, network isolation, and observability.

## Docker Compose Services

| Service | Image/build | Port | Purpose |
| --- | --- | --- | --- |
| `postgres` | `postgres:16` | `5432` | Primary PostgreSQL database. |
| `redis` | `redis:7` | `6379` | Queue and pub/sub transport. |
| `api` | `./apps/api` | `8000` | Main FastAPI backend. |
| `broker-router` | `./apps/broker-router` | `8001` | Internal Sharekhan broker gateway. |
| `worker` | `./apps/worker` | None | Redis copy job consumer. |
| `web` | `./apps/web` | `3000` | Next.js frontend. |

Postgres and Redis have health checks. API, broker-router, worker, and web load environment variables from `.env`.

Every long-running Compose service uses `restart: unless-stopped`. Docker recreates the service after a process failure and restarts it when the Docker engine returns. On Windows, Docker Desktop must also start after sign-in; the repository includes a scheduled-task installer for that purpose.

## Environment Variables

Variables in `.env.example`:

| Variable | Used by | Default/example | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | API, broker-router, worker | `postgresql+asyncpg://...` | Async PostgreSQL connection string. |
| `REDIS_URL` | API settings, broker-router WebSocket manager, worker | `redis://redis:6379/0` | Redis connection string. |
| `ENVIRONMENT` | API, broker-router | `development` | Set to `production` to enforce non-placeholder secrets at startup. |
| `JWT_SECRET` | API | Example secret | JWT signing secret. Replace for production. |
| `JWT_ALGORITHM` | API | `HS256` | JWT signing algorithm. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | API | `1440` | JWT lifetime. |
| `RUN_MIGRATIONS` | API container | `true` | When true, the API container runs `alembic upgrade head` before starting Uvicorn. |
| `APP_SECRET_KEY` | API, broker-router | Example secret | AES-GCM credential encryption key source. |
| `SHAREKHAN_BASE_URL` | Broker-router | `https://api.sharekhan.com` | Sharekhan REST base URL. |
| `SHAREKHAN_LOGIN_URL` | Broker-router | `https://api.sharekhan.com/skapi/auth/login.html` | Sharekhan login URL. |
| `SHAREKHAN_WS_URL` | Broker-router | `wss://stream.sharekhan.com/skstream/api/stream` | Sharekhan WebSocket base URL. Broker-router appends per-account `ACCESS_TOKEN` and `API_KEY` query params. |
| `SHAREKHAN_VERSION_ID` | Broker-router | `1005` | Sharekhan access-token `versionId`. Used when exchanging request tokens for access tokens. |
| `SCRIPT_MASTER_CACHE_TTL_HOURS` | API live copy manager | `24` | Hours before an exchange-scoped Script Master cache is considered stale and refreshed for missing-`scripCode` resolution. |
| `SCRIPT_MASTER_PRELOAD_ON_LOGIN` | API accounts/script master services | `true` | When true, successful Sharekhan login schedules Script Master warm-up into PostgreSQL and the API process memory index. |
| `SCRIPT_MASTER_PRELOAD_EXCHANGES` | API accounts/script master services | `NC,NF,BC,RN,MX` | Comma-separated exchanges to warm after login in addition to exchanges returned by Sharekhan profile. |
| `BROKER_ROUTER_URL` | API, worker | `http://broker-router:8001` | Internal broker-router URL. |
| `NEXT_PUBLIC_API_URL` | Web | `http://localhost:8000` | Browser-visible main API URL. |
| `CORS_ORIGINS` | API | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated or JSON-array list of allowed browser origins. |
| `BROKER_RATE_LIMIT_PER_MINUTE` | Broker-router | `120` | Per-client broker-router rate limit. |
| `PAPER_TRADING_MODE` | API settings, broker-router, worker settings | `true` | Safety switch. Broker-router enforces this for order mutation endpoints. |
| `COPY_TRADING_DRY_RUN` | API live copy manager | `true` | Safety switch for `/live-copy`. When true, copied child orders are recorded as would-send payloads instead of being sent to Sharekhan. |
| `LIVE_COPY_ORDER_DISPATCH_CONCURRENCY` | API live copy manager | `0` | Copier order dispatch limit per master event. `0` means dispatch all prepared copier orders concurrently. Positive values intentionally throttle dispatch and are logged. |

Additional settings present in code:

| Setting | Service | Default | Notes |
| --- | --- | --- | --- |
| `copy_job_queue` | Worker | `copy_jobs` | Redis list name. |
| `max_copy_retries` | Worker | `3` | Max retry count passed to copy engine. |

## Secret Key Guidance

`APP_SECRET_KEY` is converted to AES key bytes as follows:

1. If it is valid base64 and decodes to 32 bytes, that decoded value is used directly.
2. Otherwise, SHA-256 of the string is used.

For production, prefer a random 32-byte value encoded with base64 and store it in a secret manager. Do not rotate it casually because existing encrypted credentials and tokens require the same key to decrypt.

If `APP_SECRET_KEY` changes after accounts already exist, account rows can appear as `CREDENTIALS_LOCKED`. The account list will still load, but broker login/API requests for that account require the operator to edit the account, re-enter the API Key and Secure Key, and re-enter or clear optional vendor/proxy details so the app can encrypt them with the active key.

## Local Setup

1. Copy environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

2. Edit `.env` and set strong secrets.

3. Build and start:

```bash
docker compose up --build
```

4. Run migrations:

```bash
docker compose exec api alembic upgrade head
```

With the default `RUN_MIGRATIONS=true`, the API container also runs `alembic upgrade head` before Uvicorn starts. Keep this enabled for local Compose. In multi-replica production deployments, prefer a single explicit migration job and set `RUN_MIGRATIONS=false` on normal API replicas.

5. Open:

| App | URL |
| --- | --- |
| Frontend | `http://localhost:3000` |
| Main API docs | `http://localhost:8000/docs` |
| Broker-router docs | `http://localhost:8001/docs` |

For Sharekhan API login, configure the Sharekhan application callback URL to the frontend callback route:

| Environment | Callback URL |
| --- | --- |
| Local Compose | `http://localhost:3000/sharekhan/callback` |
| Production | `https://your-domain.com/sharekhan/callback` |

## Service Commands

Start all services:

```bash
docker compose up --build
```

Start only infrastructure:

```bash
docker compose up postgres redis
```

Run API migrations:

```bash
docker compose exec api alembic upgrade head
```

Run tests:

```bash
docker compose run --rm api python -m pytest
docker compose run --rm broker-router python -m pytest
docker compose run --rm worker python -m pytest
```

View logs:

```bash
docker compose logs -f api
docker compose logs -f broker-router
docker compose logs -f worker
docker compose logs -f web
```

## Windows Auto-Start After Reboot

The repository provides two complementary safeguards:

1. `restart: unless-stopped` is configured for Postgres, Redis, API, broker-router, worker, and web.
2. A per-user Windows Scheduled Task starts Docker Desktop when needed, waits for the Docker engine, and runs `docker compose up -d` from this repository after sign-in.

Install the task once from a normal PowerShell window in the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install-windows-autostart.ps1 -RunNow
```

The default task name is `SharekhanCopyTrader-Docker-Autostart`. `-RunNow` starts it immediately for a smoke test; omit that switch when only installing it.

Verify the task and containers:

```powershell
Get-ScheduledTask -TaskName SharekhanCopyTrader-Docker-Autostart
docker compose ps
Get-Content .\logs\docker-autostart.log -Tail 50
```

The log file is ignored by Git. The task runs for the Windows user who installed it and starts after that user signs in, which matches Docker Desktop's per-user runtime model. If the repository is moved, rerun the installer from the new path so the task action is updated.

Remove auto-start without stopping currently running containers:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\uninstall-windows-autostart.ps1
```

Operational notes:

- Keep Docker Desktop installed in its default location or ensure `docker.exe` is on `PATH`.
- The runner waits up to 180 seconds for the Docker engine. Failures are recorded in `logs\docker-autostart.log`.
- `docker compose down` removes the containers; the next logon task recreates them.
- `docker compose stop` stops them temporarily, but the next logon task starts them again through `docker compose up -d`.
- To prevent automatic startup for maintenance, disable the scheduled task or uninstall it before stopping the stack.

## Production Deployment Checklist

### Network

- Do not expose broker-router publicly.
- Do not expose Postgres or Redis publicly.
- Allow browser traffic only to web and main API.
- Allow worker and main API to reach broker-router over a private network.

### Secrets

- Replace all example secrets.
- Store `.env` values in a secret manager or platform environment store.
- Use separate secrets per environment.
- Back up `APP_SECRET_KEY` securely. Losing it means encrypted broker credentials cannot be decrypted.
- Back up `JWT_SECRET` as well; user JWTs depend on it during their validity window.

### Database

- Run Alembic migrations as part of deployment.
- Enable automated backups and restore drills.
- Use managed Postgres or persistent volumes with backup policy.
- Monitor connection counts and query latency.

### Redis

- Use authentication/TLS when outside a private local network.
- Monitor queue depth for `copy_jobs`.
- Monitor pub/sub stream error channel if stream processing is enabled.

### Broker Safety

- Keep `PAPER_TRADING_MODE=true` in every non-production environment.
- Keep `COPY_TRADING_DRY_RUN=true` until dry-run live copy sessions have been reviewed.
- Require explicit approval and a change record before setting `PAPER_TRADING_MODE=false` or `COPY_TRADING_DRY_RUN=false`.
- Validate risk settings and order payloads with real account credentials in paper mode first.
- Start with small quantity/capital limits when enabling live mode.

### Observability

- Add structured logs around broker-router requests and worker copy results.
- Capture metrics for queue depth, retry counts, failed orders, broker latency, and rate-limit rejections.
- Add alerting for worker exit, Redis connectivity, broker-router health, and failed copy order spikes.

## Scaling Notes

| Component | Scaling consideration |
| --- | --- |
| Web | Stateless and horizontally scalable. |
| Main API | Mostly stateless; database pool sizing matters. |
| Broker-router | In-memory rate limiter and WebSocket connection map are per instance. Multiple replicas need sticky routing or shared coordination for stream sessions. |
| Worker | Multiple workers can consume the same Redis list, but duplicate protection depends on `copy_orders.idempotency_key`. Race conditions can still create unique constraint errors if two jobs carry the same target simultaneously. |
| Redis | Queue and stream pub/sub are central coordination points. |
| Postgres | Primary consistency boundary. |

## Live Trading Readiness

Before live trading:

1. Verify Sharekhan login callback and automatic access-token/profile exchange for all accounts.
2. Confirm each account has a stored `customer_id` and `login_id` after callback token exchange, or manually enter them if Sharekhan did not return those fields.
3. Confirm copy groups and settings map exactly to intended accounts.
4. Confirm account proxy details are correct when a proxy is required.
5. Use strict `max_qty` and `max_order_value`.
6. Confirm `allowed_symbols`, `blocked_symbols`, and product mappings.
7. Run synthetic copy jobs in paper mode and inspect `copy_orders`.
8. Run a `/live-copy` dry-run session and inspect `master_trade_events` plus `copied_trade_orders`.
9. Verify broker-router order payloads match Sharekhan expectations.
10. Confirm operational monitoring is active.
11. Switch `PAPER_TRADING_MODE=false` and `COPY_TRADING_DRY_RUN=false` only during a controlled market session with manual oversight.

## Backup And Restore Notes

Back up:

- PostgreSQL database.
- Production environment variables, especially `APP_SECRET_KEY`.
- Deployment configuration.

Restore validation should include:

- API can decrypt an existing account secret.
- Broker-router can load an account and generate login URL.
- Dashboard and order read APIs return expected data.
- Worker can insert a copy order for a known master order in a test environment.
