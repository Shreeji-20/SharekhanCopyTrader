"""
Opt-in smoke checks for the Sharekhan workflows exposed by the main API.

Required environment:
  SMOKE_JWT          Bearer token from the app login flow
  SMOKE_ACCOUNT_ID   Logged-in broker account id

Optional environment:
  SMOKE_API_BASE=http://localhost:8000
  SMOKE_EXCHANGE=NC
  SMOKE_SCRIPCODE=2475
  SMOKE_INTERVAL=5minute
  SMOKE_RUN_STREAM=false
  SMOKE_PLACE_ORDER=false
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any


API_BASE = os.getenv("SMOKE_API_BASE", "http://localhost:8000").rstrip("/")
JWT = os.getenv("SMOKE_JWT")
ACCOUNT_ID = os.getenv("SMOKE_ACCOUNT_ID")
EXCHANGE = os.getenv("SMOKE_EXCHANGE", "NC")
SCRIPCODE = os.getenv("SMOKE_SCRIPCODE", "2475")
INTERVAL = os.getenv("SMOKE_INTERVAL", "5minute")


def request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Authorization": f"Bearer {JWT}", "Content-Type": "application/json"}
    req = urllib.request.Request(f"{API_BASE}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed with HTTP {exc.code}: {detail}") from exc


def require_env() -> None:
    missing = [name for name, value in {"SMOKE_JWT": JWT, "SMOKE_ACCOUNT_ID": ACCOUNT_ID}.items() if not value]
    if missing:
        raise SystemExit(f"Missing required environment: {', '.join(missing)}")


def main() -> None:
    require_env()
    checks: list[tuple[str, str]] = [
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/profile"),
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/funds/NSE"),
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/reports"),
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/trades"),
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/holdings"),
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/master/{EXCHANGE}"),
        ("GET", f"/accounts/{ACCOUNT_ID}/sharekhan/historical/{EXCHANGE}/{SCRIPCODE}/{INTERVAL}"),
    ]
    for method, path in checks:
        result = request(method, path)
        print(f"OK {method} {path}: {str(result)[:180]}")

    if os.getenv("SMOKE_RUN_STREAM", "").lower() == "true":
        print("OK POST ws/connect:", request("POST", f"/accounts/{ACCOUNT_ID}/sharekhan/ws/connect"))
        print(
            "OK POST ws/subscribe:",
            request("POST", f"/accounts/{ACCOUNT_ID}/sharekhan/ws/subscribe", {"exchange": EXCHANGE, "symbols": [SCRIPCODE]}),
        )

    if os.getenv("SMOKE_PLACE_ORDER", "").lower() == "true":
        account = request("GET", f"/accounts/{ACCOUNT_ID}")
        payload = {
            "customerId": account.get("customer_id"),
            "channelUser": account.get("login_id"),
            "scripCode": int(SCRIPCODE),
            "tradingSymbol": os.getenv("SMOKE_TRADING_SYMBOL", "ONGC"),
            "exchange": EXCHANGE,
            "transactionType": os.getenv("SMOKE_SIDE", "B"),
            "quantity": int(os.getenv("SMOKE_QTY", "1")),
            "disclosedQty": 0,
            "price": os.getenv("SMOKE_PRICE", "0"),
            "triggerPrice": os.getenv("SMOKE_TRIGGER_PRICE", "0"),
            "rmsCode": "ANY",
            "afterHour": "N",
            "orderType": "NORMAL",
            "validity": "GFD",
            "requestType": "NEW",
            "productType": "INVESTMENT",
        }
        print("OK POST order/place:", request("POST", f"/accounts/{ACCOUNT_ID}/sharekhan/orders/place", payload))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
