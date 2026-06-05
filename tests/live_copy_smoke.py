"""
Opt-in smoke checks for live copy trading session endpoints.

Required environment:
  SMOKE_JWT                Bearer token from the app login flow
  SMOKE_MASTER_ACCOUNT_ID  Logged-in MASTER broker account id
  SMOKE_COPY_GROUP_IDS     Comma-separated copy group ids for that master

Optional environment:
  SMOKE_API_BASE=http://localhost:8000
  SMOKE_START_COPY_SESSION=false
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
MASTER_ACCOUNT_ID = os.getenv("SMOKE_MASTER_ACCOUNT_ID")
COPY_GROUP_IDS = [value.strip() for value in os.getenv("SMOKE_COPY_GROUP_IDS", "").split(",") if value.strip()]


def request(method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any] | list[Any]:
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
    missing = []
    if not JWT:
        missing.append("SMOKE_JWT")
    if not MASTER_ACCOUNT_ID:
        missing.append("SMOKE_MASTER_ACCOUNT_ID")
    if not COPY_GROUP_IDS:
        missing.append("SMOKE_COPY_GROUP_IDS")
    if missing:
        raise SystemExit(f"Missing required environment: {', '.join(missing)}")


def main() -> None:
    require_env()
    validation_payload = {"master_account_id": MASTER_ACCOUNT_ID, "copy_group_ids": COPY_GROUP_IDS}
    print("OK validate:", json.dumps(request("POST", "/copy-groups/validate", validation_payload), indent=2))
    print("OK sessions:", str(request("GET", "/copy-sessions"))[:500])

    if os.getenv("SMOKE_START_COPY_SESSION", "").lower() == "true":
        session = request(
            "POST",
            "/copy-sessions/start",
            {
                "master_account_id": MASTER_ACCOUNT_ID,
                "copy_group_ids": COPY_GROUP_IDS,
                "dry_run": True,
                "allow_duplicate_copiers": False,
            },
        )
        if not isinstance(session, dict):
            raise RuntimeError("Unexpected copy-session start response")
        print("OK start dry-run session:", session)
        session_id = session["id"]
        print("OK events:", request("GET", f"/copy-sessions/{session_id}/events"))
        print("OK copied-orders:", request("GET", f"/copy-sessions/{session_id}/copied-orders"))
        print("OK stop:", request("POST", f"/copy-sessions/{session_id}/stop"))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
