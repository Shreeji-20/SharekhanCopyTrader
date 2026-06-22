from __future__ import annotations

import logging
import uuid
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from app.core.config import get_settings
from app.db.session import AsyncSessionLocal
from app.services.script_master import script_master_service

logger = logging.getLogger(__name__)


def script_master_preload_exchanges_from_profile(
    profile: Mapping[str, Any] | None,
    configured_exchanges: Sequence[str],
) -> list[str]:
    return _unique_exchange_codes(
        [
            *_extract_profile_exchanges(profile),
            *configured_exchanges,
        ]
    )


async def warm_script_master_after_login(account_id: uuid.UUID, profile: Mapping[str, Any] | None = None) -> None:
    settings = get_settings()
    if not settings.script_master_preload_on_login:
        logger.info("script_master.login_preload_disabled", extra={"account_id": str(account_id)})
        return

    exchanges = script_master_preload_exchanges_from_profile(profile, settings.script_master_preload_exchange_codes)
    if not exchanges:
        logger.info("script_master.login_preload_skipped", extra={"account_id": str(account_id), "reason": "no_exchanges"})
        return

    logger.info(
        "script_master.login_preload_started",
        extra={"account_id": str(account_id), "exchanges": exchanges},
    )
    for exchange in exchanges:
        async with AsyncSessionLocal() as db:
            try:
                refreshed = await script_master_service.ensure_exchange_cache(
                    db,
                    exchange,
                    account_id,
                    refresh_stale=True,
                )
                await db.commit()
                cache_info = script_master_service.memory_cache_info(exchange)
                logger.info(
                    "script_master.login_preload_exchange_ready",
                    extra={
                        "account_id": str(account_id),
                        "exchange": exchange,
                        "refreshed_from_broker": refreshed,
                        **cache_info,
                    },
                )
            except Exception:
                await db.rollback()
                logger.exception(
                    "script_master.login_preload_exchange_failed",
                    extra={"account_id": str(account_id), "exchange": exchange},
                )
    logger.info("script_master.login_preload_completed", extra={"account_id": str(account_id), "exchanges": exchanges})


def scheduled_login_preload_exchanges(profile: Mapping[str, Any] | None = None) -> list[str]:
    settings = get_settings()
    if not settings.script_master_preload_on_login:
        return []
    return script_master_preload_exchanges_from_profile(profile, settings.script_master_preload_exchange_codes)


def _extract_profile_exchanges(profile: Mapping[str, Any] | None) -> list[str]:
    if not isinstance(profile, Mapping):
        return []
    values: list[Any] = [profile.get("exchanges")]
    for nested_key in ("data", "profile"):
        nested = profile.get(nested_key)
        if isinstance(nested, Mapping):
            values.append(nested.get("exchanges"))
    return _flatten_exchange_values(values)


def _flatten_exchange_values(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            output.extend(part.strip() for part in value.split(","))
            continue
        if isinstance(value, Iterable):
            output.extend(str(part).strip() for part in value)
            continue
        output.append(str(value).strip())
    return output


def _unique_exchange_codes(values: Iterable[str]) -> list[str]:
    exchanges: list[str] = []
    seen: set[str] = set()
    for value in values:
        exchange = "".join(ch for ch in str(value).strip().upper() if ch.isalnum())
        if not exchange or exchange in seen:
            continue
        seen.add(exchange)
        exchanges.append(exchange)
    return exchanges
