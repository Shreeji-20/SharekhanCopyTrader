import uuid
from typing import Any

import httpx

from app.config import get_settings


class BrokerRouterClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or get_settings().broker_router_url).rstrip("/")

    async def place_order(self, account_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(f"/sharekhan/accounts/{account_id}/orders/place", json=payload)
            response.raise_for_status()
            return response.json()

