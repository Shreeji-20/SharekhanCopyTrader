from fastapi import APIRouter

from app.core.config import get_settings
from app.dependencies import CurrentUser
from app.services.broker_router import BrokerRouterClient

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/trading-mode")
async def trading_mode(_: CurrentUser) -> dict[str, object]:
    settings = get_settings()
    broker_health: dict[str, object] = {}
    broker_paper_mode: bool | None = None
    try:
        broker_health = await BrokerRouterClient().get("/health")
        value = broker_health.get("paper_trading_mode")
        broker_paper_mode = bool(value) if value is not None else None
    except Exception as exc:
        broker_health = {"ok": False, "error": str(exc)}
    live_orders_enabled = (
        settings.paper_trading_mode is False
        and settings.copy_trading_dry_run is False
        and broker_paper_mode is False
    )
    return {
        "api_paper_trading_mode": settings.paper_trading_mode,
        "copy_trading_dry_run": settings.copy_trading_dry_run,
        "broker_router_paper_trading_mode": broker_paper_mode,
        "live_orders_enabled": live_orders_enabled,
        "broker_router_health": broker_health,
        "notes": [
            "Live copied orders require session dry_run=false.",
            "Live copied orders are blocked if API PAPER_TRADING_MODE=true.",
            "Live copied orders are blocked if COPY_TRADING_DRY_RUN=true.",
            "Live copied orders are blocked if broker-router PAPER_TRADING_MODE=true.",
        ],
    }
