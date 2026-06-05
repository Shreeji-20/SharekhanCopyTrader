# Copy Worker

The copy worker lives in `apps/worker`. It is an async Python process that consumes copy jobs from Redis and places copy orders through broker-router after risk validation.

## Runtime

| Item | Value |
| --- | --- |
| Entry point | `python -m app.main` |
| Dockerfile | `apps/worker/Dockerfile` |
| Queue | Redis list named by `copy_job_queue`, default `copy_jobs` |
| Broker dependency | `BROKER_ROUTER_URL`, default `http://broker-router:8001` |
| Persistence | Inserts into `copy_orders` |

## Core Modules

| File | Purpose |
| --- | --- |
| `app/main.py` | Redis loop, job parsing, engine wiring. |
| `app/risk.py` | Domain dataclasses, sizing, market-hours logic, risk filters, payload construction. |
| `app/engine.py` | Per-target orchestration, duplicate checks, retries, save callback. |
| `app/repository.py` | `copy_orders` idempotency lookup and insert. |
| `app/broker_router.py` | HTTP client for broker-router order placement. |
| `app/config.py` | Worker settings. |

## Queue Processing

`run_forever` performs:

1. Connect to Redis using `REDIS_URL`.
2. Block on `BRPOP copy_jobs` with a 5 second timeout.
3. Decode the popped JSON string.
4. Call `handle_job`.
5. Continue forever until the process is stopped.

There is no dead-letter queue in the current implementation. Exceptions from `handle_job` would exit the current processing call and should be supervised by the container runtime.

## Job Shape

The worker expects a JSON object with a `master_order` and a list of `targets`.

```json
{
  "master_order": {
    "id": "00000000-0000-0000-0000-000000000001",
    "broker_order_id": "M-123",
    "exchange": "NC",
    "scrip_code": "2475",
    "trading_symbol": "ONGC",
    "transaction_type": "B",
    "quantity": 100,
    "price": "150.00",
    "trigger_price": "0",
    "order_type": "NORMAL",
    "product_type": "INVESTMENT",
    "request_type": "NEW",
    "raw_payload": {
      "rmsCode": "ANY",
      "afterHour": "N",
      "validity": "GFD"
    }
  },
  "targets": [
    {
      "account": {
        "id": "00000000-0000-0000-0000-000000000002",
        "customer_id": "CUSTOMER_ID",
        "login_id": "LOGIN_ID",
        "is_active": true,
        "has_token": true,
        "capital": "100000"
      },
      "settings": {
        "is_enabled": true,
        "sizing_mode": "MULTIPLIER",
        "multiplier": "0.5",
        "fixed_qty": null,
        "capital_percent": null,
        "max_qty": 100,
        "max_order_value": "50000",
        "allowed_symbols": ["ONGC"],
        "blocked_symbols": [],
        "allowed_transaction_types": ["B", "S"],
        "allowed_product_types": ["INVESTMENT"],
        "product_type_map": {},
        "price_mode": "SAME_PRICE",
        "max_slippage_percent": null,
        "is_auto_squareoff_enabled": false
      }
    }
  ],
  "enforce_market_hours": true
}
```

Important precondition: `master_order.id` must already exist in the `master_orders` table because `copy_orders.master_order_id` has a foreign key.

## Domain Objects

### `MasterOrder`

Normalized master order data used for risk calculation and payload creation.

### `CopyAccount`

Worker-side account view:

- `id`
- `customer_id`
- `login_id`
- `is_active`
- `has_token`
- optional `capital`

The worker trusts the job producer to populate these fields accurately. It does not reload broker accounts or copy settings from PostgreSQL.

### `CopySettings`

Worker-side copy configuration:

- Enable flag.
- Sizing mode and sizing values.
- Quantity and notional caps.
- Symbol, transaction type, and product type filters.
- Product type mapping.
- Price mode and slippage.
- Auto square-off flag, stored but not acted on by current worker code.

## Risk Validation

`validate_risk` rejects a target with `RiskRejected` when any rule fails.

| Rule | Rejection reason |
| --- | --- |
| Copy account inactive | `account is inactive` |
| Missing broker token | `access token is missing` |
| Copy setting disabled | `copy setting is disabled` |
| Market closed and enforcement enabled | `market is closed` |
| Symbol in blocked list | `symbol is blocked` |
| Allowed symbols configured and symbol not included | `symbol is not allowed` |
| Transaction type not allowed | `transaction type is not allowed` |
| Product type not allowed | `product type is not allowed` |
| Calculated quantity <= 0 | `calculated quantity must be greater than zero` |
| Quantity cap exceeded | `quantity exceeds max quantity` |
| Order value cap exceeded | `order value exceeds max order value` |

Market hours are checked in `Asia/Kolkata`:

- Monday to Friday only.
- Inclusive time window from `09:15` to `15:30`.

Set `enforce_market_hours=false` in a job to bypass this check, mainly for tests or controlled simulations.

## Sizing Modes

| Mode | Calculation |
| --- | --- |
| `SAME_QTY` | Copy master order quantity exactly. |
| `MULTIPLIER` | `floor(master.quantity * multiplier)`. |
| `FIXED_QTY` | Use `fixed_qty`; reject when missing. |
| `PERCENT_CAPITAL` | `floor((copy_account.capital * capital_percent / 100) / master.price)`. |

`PERCENT_CAPITAL` rejects when account capital, capital percent, or positive price is missing.

## Price Modes

| Mode | Calculation |
| --- | --- |
| `SAME_PRICE` | Copy master price. |
| `MARKET` | Set price to `0`. |
| `LIMIT_WITH_SLIPPAGE` | For buys, `price * (1 + slippage/100)`. For sells, `price * (1 - slippage/100)`. Result is rounded to 2 decimals. |

## Copy Payload

`copy_order_payload` builds the body sent to broker-router:

```json
{
  "customerId": "COPY_CUSTOMER_ID",
  "scripCode": 2475,
  "tradingSymbol": "ONGC",
  "exchange": "NC",
  "transactionType": "B",
  "quantity": 50,
  "disclosedQty": 0,
  "price": "150.00",
  "triggerPrice": "0",
  "rmsCode": "ANY",
  "afterHour": "N",
  "orderType": "NORMAL",
  "channelUser": "COPY_LOGIN_ID",
  "validity": "GFD",
  "requestType": "NEW",
  "productType": "INVESTMENT"
}
```

Values such as `rmsCode`, `afterHour`, and `validity` fall back to defaults when absent from `master_order.raw_payload`.

## Idempotency

Before risk checks, the engine computes:

```text
sha256("{master_order.id}:{copy_account.id}:{master_order.request_type.upper()}")
```

If `copy_orders` already contains this key:

- The target is not sent to broker-router.
- A `SKIPPED` copy order is saved with `error_message="duplicate idempotency key"`.

The database also has a unique constraint on `copy_orders.idempotency_key`.

## Retry Behavior

The engine calls broker-router through `BrokerRouterClient.place_order`.

On exception:

- It retries while `attempt < max_retries`.
- Sleep duration is exponential: `1`, `2`, `4`, ... seconds from `2**attempt`.
- With default `max_copy_retries=3`, the engine can attempt up to 4 total sends.
- On final failure, it saves status `FAILED`, the last error string, and `retry_count=max_retries`.

On success:

- It reads `broker_order_id` from `response.normalized.broker_order_id` or `response.data.orderId`.
- It saves status `SUCCESS`.
- `retry_count` records the successful attempt number, so `0` means first try succeeded.

## Persistence

`CopyOrderRepository.save` inserts:

- A new UUID `id`.
- The `master_order_id` from the job.
- Target `copy_account_id`.
- Result status and broker order ID.
- Calculated quantity.
- Calculated price parsed from the request payload.
- Request and response payloads.
- Error message and retry count.
- Idempotency key.
- `created_at` and `updated_at`.

The worker does not update existing rows. It only inserts.

## Settings

| Setting | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Compose Postgres URL | Used by repository. |
| `REDIS_URL` | `redis://redis:6379/0` | Used for queue consumption. |
| `BROKER_ROUTER_URL` | `http://broker-router:8001` | Used for order placement. |
| `PAPER_TRADING_MODE` | `true` | Present in settings but broker-router is the service that enforces paper order behavior. |
| `copy_job_queue` | `copy_jobs` | Redis list name. |
| `max_copy_retries` | `3` | Retry count passed to engine. |

## Current Limitations

- No built-in master order detector or job producer is included.
- No dead-letter queue is implemented.
- No per-job audit log is written; results are captured in `copy_orders`.
- The worker trusts account/settings data in the job instead of loading fresh values from the database.
- It processes targets sequentially within each job.
- It only calls broker-router's place endpoint, even though `request_type` is included in the payload. Modify/cancel propagation would need endpoint selection logic.
