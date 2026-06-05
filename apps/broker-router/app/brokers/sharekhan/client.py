from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import httpx


class SharekhanApiError(Exception):
    def __init__(self, status_code: int, detail: str, body: Any = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.body = body


class SharekhanRawClient:
    BASE_URL = "https://api.sharekhan.com"
    LOGIN_URL = "https://api.sharekhan.com/skapi/auth/login.html"

    ROUTES = {
        "access_token": "/skapi/services/access/token",
        "funds": "/skapi/services/limitstmt/{exchange}/{customerId}",
        "orders": "/skapi/services/orders",
        "reports": "/skapi/services/reports/{customerId}",
        "trades": "/skapi/services/trades/{customerId}",
        "order_details": "/skapi/services/reports/{exchange}/{customerId}/{orderId}",
        "order_trades": "/skapi/services/reports/{exchange}/{customerId}/{orderId}/trades",
        "holdings": "/skapi/services/holdings/{customerId}",
        "master": "/skapi/services/master/{exchange}",
        "historical": "/skapi/services/historical/{exchange}/{scripcode}/{interval}",
    }

    def __init__(
        self,
        *,
        api_key: str,
        access_token: str | None = None,
        customer_id: str | None = None,
        login_id: str | None = None,
        vendor_key: str | None = None,
        proxy_url: str | None = None,
        base_url: str | None = None,
        login_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.access_token = access_token
        self.customer_id = customer_id
        self.login_id = login_id
        self.vendor_key = vendor_key
        self.proxy_url = proxy_url
        self.base_url = (base_url or self.BASE_URL).rstrip("/")
        self.login_url = login_url or self.LOGIN_URL

    def build_url(self, route_name: str, **path_params: str) -> str:
        route = self.ROUTES[route_name].format(**path_params)
        return f"{self.base_url}{route}"

    def build_headers(self) -> dict[str, str]:
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["access-token"] = self.access_token
        if self.vendor_key:
            headers["vendor-key"] = self.vendor_key
        return headers

    def generate_login_url(self, *, state: str | None = None) -> str:
        query = {"api_key": self.api_key}
        if self.vendor_key:
            query["vendor_key"] = self.vendor_key
        if state:
            query["state"] = state
        return f"{self.login_url}?{urlencode(query)}"

    async def _request(self, method: str, route_name: str, **kwargs: Any) -> dict[str, Any]:
        path_params = kwargs.pop("path_params", {})
        url = self.build_url(route_name, **path_params)
        async with httpx.AsyncClient(timeout=30, proxy=self.proxy_url) as client:
            response = await client.request(method, url, headers=self.build_headers(), **kwargs)
            if response.is_error:
                raise SharekhanApiError(response.status_code, _response_error_detail(response), _response_body(response))
            return response.json()

    async def exchange_access_token(
        self,
        *,
        final_request_token: str,
        state: str,
        version_id: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "apiKey": self.api_key,
            "requestToken": final_request_token,
            "state": state,
            "versionId": version_id,
        }
        if self.vendor_key:
            payload["vendorkey"] = self.vendor_key
        return await self._request("POST", "access_token", json=payload)

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = _json_ready(payload | {"requestType": "NEW"})
        return await self._request("POST", "orders", json=payload)

    async def modify_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = _json_ready(payload | {"requestType": "MODIFY"})
        return await self._request("POST", "orders", json=payload)

    async def cancel_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload = _json_ready(payload | {"requestType": "CANCEL"})
        return await self._request("POST", "orders", json=payload)

    async def funds(self, exchange: str, customer_id: str) -> dict[str, Any]:
        return await self._request("GET", "funds", path_params={"exchange": exchange, "customerId": customer_id})

    async def reports(self, customer_id: str) -> dict[str, Any]:
        return await self._request("GET", "reports", path_params={"customerId": customer_id})

    async def trades(self, customer_id: str) -> dict[str, Any]:
        return await self._request("GET", "trades", path_params={"customerId": customer_id})

    async def order_details(self, exchange: str, customer_id: str, order_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "order_details",
            path_params={"exchange": exchange, "customerId": customer_id, "orderId": order_id},
        )

    async def order_trades(self, exchange: str, customer_id: str, order_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "order_trades",
            path_params={"exchange": exchange, "customerId": customer_id, "orderId": order_id},
        )

    async def holdings(self, customer_id: str) -> dict[str, Any]:
        return await self._request("GET", "holdings", path_params={"customerId": customer_id})

    async def master(self, exchange: str) -> dict[str, Any]:
        return await self._request("GET", "master", path_params={"exchange": exchange})

    async def historical(self, exchange: str, scripcode: str, interval: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            "historical",
            path_params={"exchange": exchange, "scripcode": scripcode, "interval": interval},
        )


def _json_ready(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: str(value) if isinstance(value, Decimal) else value for key, value in payload.items() if value is not None}


def _response_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _response_error_detail(response: httpx.Response) -> str:
    body = _response_body(response)
    if isinstance(body, dict):
        detail = body.get("message") or body.get("detail") or body.get("error")
        if detail:
            return str(detail)
    if isinstance(body, str) and body.strip():
        return body.strip()
    return f"Sharekhan API request failed with HTTP {response.status_code}"


def normalize_order_response(response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data") if isinstance(response.get("data"), dict) else response
    return {
        "broker_order_id": data.get("orderId") or data.get("order_id") or data.get("orderNo"),
        "status": data.get("status") or data.get("orderStatus") or response.get("status"),
        "message": data.get("message") or response.get("message"),
        "raw": response,
    }
