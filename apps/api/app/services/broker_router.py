import uuid
from typing import Any

from fastapi import HTTPException
import httpx

from app.core.config import get_settings


class BrokerRouterClient:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or get_settings().broker_router_url).rstrip("/")

    async def post(self, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.post(path, json=json or {})
            self._raise_for_broker_error(response)
            return response.json()

    async def get(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30) as client:
            response = await client.get(path)
            self._raise_for_broker_error(response)
            return response.json()

    @staticmethod
    def _raise_for_broker_error(response: httpx.Response) -> None:
        if response.is_success:
            return
        try:
            body = response.json()
        except ValueError:
            body = response.text
        if isinstance(body, dict) and "detail" in body:
            detail = body["detail"]
        else:
            detail = body or response.reason_phrase
        raise HTTPException(status_code=response.status_code, detail=detail)

    async def login_url(self, account_id: uuid.UUID, state: str | None = None) -> dict[str, Any]:
        payload = {"account_id": str(account_id)}
        if state:
            payload["state"] = state
        return await self.post(f"/sharekhan/login-url", payload)

    async def exchange_token(self, account_id: uuid.UUID, request_token: str) -> dict[str, Any]:
        return await self.post(
            "/sharekhan/token/exchange",
            {"account_id": str(account_id), "request_token": request_token},
        )

    async def profile(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/profile")

    async def place_order(self, account_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/sharekhan/accounts/{account_id}/orders/place", payload)

    async def modify_order(self, account_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/sharekhan/accounts/{account_id}/orders/modify", payload)

    async def cancel_order(self, account_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/sharekhan/accounts/{account_id}/orders/cancel", payload)

    async def funds(self, account_id: uuid.UUID, exchange: str) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/funds/{exchange}")

    async def reports(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/reports")

    async def trades(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/trades")

    async def order_details(self, account_id: uuid.UUID, exchange: str, order_id: str) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/orders/{exchange}/{order_id}")

    async def order_trades(self, account_id: uuid.UUID, exchange: str, order_id: str) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/orders/{exchange}/{order_id}/trades")

    async def holdings(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.get(f"/sharekhan/accounts/{account_id}/holdings")

    async def master(self, exchange: str, account_id: uuid.UUID | None = None) -> dict[str, Any]:
        query = f"?account_id={account_id}" if account_id else ""
        return await self.get(f"/sharekhan/master/{exchange}{query}")

    async def historical(
        self,
        exchange: str,
        scripcode: str,
        interval: str,
        account_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        query = f"?account_id={account_id}" if account_id else ""
        return await self.get(f"/sharekhan/historical/{exchange}/{scripcode}/{interval}{query}")

    async def ws_connect(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.post(f"/sharekhan/ws/connect/{account_id}")

    async def ws_status(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.get(f"/sharekhan/ws/status/{account_id}")

    async def ws_subscribe(self, account_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/sharekhan/ws/subscribe/{account_id}", payload)

    async def ws_unsubscribe(self, account_id: uuid.UUID, payload: dict[str, Any]) -> dict[str, Any]:
        return await self.post(f"/sharekhan/ws/unsubscribe/{account_id}", payload)

    async def ws_disconnect(self, account_id: uuid.UUID) -> dict[str, Any]:
        return await self.post(f"/sharekhan/ws/disconnect/{account_id}")
