from __future__ import annotations

import csv
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import Any, Iterable, Sequence

from sqlalchemy import delete, func, insert, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ScriptMasterInstrument, utcnow
from app.services.broker_router import BrokerRouterClient

logger = logging.getLogger(__name__)

RESOLVED = "RESOLVED"
UNRESOLVED = "UNRESOLVED"
AMBIGUOUS = "AMBIGUOUS"
CACHE_EMPTY = "CACHE_EMPTY"

SCRIP_CODE_FIELDS = (
    "scripCode",
    "ScripCode",
    "scrip_code",
    "ScripToken",
    "Token",
    "ExchangeScripCode",
    "exchangeScripCode",
    "SEM_SMST_SECURITY_ID",
    "securityId",
)
TRADING_SYMBOL_FIELDS = (
    "tradingSymbol",
    "TradingSymbol",
    "trading_symbol",
    "symbol",
    "Symbol",
    "SEM_TRADING_SYMBOL",
    "semTradingSymbol",
    "companySymbol",
)
SYMBOL_NAME_FIELDS = (
    "symbolName",
    "SymbolName",
    "name",
    "Name",
    "SEM_CUSTOM_SYMBOL",
    "SEM_SYMBOL_NAME",
    "companyName",
    "CompanyName",
)
UNDERLYING_SYMBOL_FIELDS = (
    "underlying",
    "Underlying",
    "underlyingSymbol",
    "UnderlyingSymbol",
    "SEM_UNDERLYING_SYMBOL",
    "rootSymbol",
)
EXCHANGE_FIELDS = (
    "exchange",
    "Exchange",
    "exchangeCode",
    "ExchangeCode",
    "exch",
    "Exch",
    "SEM_EXM_EXCH_ID",
)
SEGMENT_FIELDS = (
    "segment",
    "Segment",
    "segmentCode",
    "SegmentCode",
    "SEM_SEGMENT",
    "SEM_SEGMENT_CODE",
)
INSTRUMENT_FIELDS = (
    "instrumentType",
    "InstrumentType",
    "instrument_type",
    "instrument",
    "Instrument",
    "insType",
    "InsType",
    "SEM_INSTRUMENT_NAME",
)
OPTION_FIELDS = (
    "optionType",
    "OptionType",
    "option_type",
    "cpType",
    "CPType",
    "SEM_OPTION_TYPE",
)
STRIKE_FIELDS = (
    "strikePrice",
    "StrikePrice",
    "strike_price",
    "strike",
    "Strike",
    "SEM_STRIKE_PRICE",
)
EXPIRY_FIELDS = (
    "expiry",
    "Expiry",
    "expiryDate",
    "ExpiryDate",
    "expDate",
    "ExpDate",
    "SEM_EXPIRY_DATE",
)
LOT_SIZE_FIELDS = (
    "lotSize",
    "LotSize",
    "lot_size",
    "marketLot",
    "MarketLot",
    "SEM_LOT_UNITS",
)
ISIN_FIELDS = ("isin", "ISIN", "isinCode", "IsinCode", "SEM_ISIN_CODE")


@dataclass(frozen=True)
class ScriptMasterLookup:
    symbol: str
    exchange: str
    segment: str | None = None
    instrument_type: str | None = None
    option_type: str | None = None
    strike_price: Decimal | None = None
    expiry_date: date | str | None = None
    lot_size: int | None = None
    isin: str | None = None


@dataclass(frozen=True)
class NormalizedScriptMasterRow:
    exchange: str
    segment: str | None
    scrip_code: str
    trading_symbol: str
    symbol_name: str | None
    underlying_symbol: str | None
    instrument_type: str | None
    option_type: str | None
    strike_price: Decimal | None
    expiry_date: date | None
    lot_size: int | None
    isin: str | None
    raw_payload_json: dict[str, Any]


@dataclass(frozen=True)
class ScriptMasterResolution:
    status: str
    message: str
    scrip_code: int | None = None
    record_id: uuid.UUID | None = None
    candidates: tuple[dict[str, Any], ...] = ()
    refreshed: bool = False

    @property
    def resolved(self) -> bool:
        return self.status == RESOLVED and self.scrip_code is not None

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "scripCode": self.scrip_code,
            "record_id": str(self.record_id) if self.record_id else None,
            "candidates": list(self.candidates),
            "refreshed": self.refreshed,
        }


def normalize_script_master_response(response: Any, exchange: str) -> list[NormalizedScriptMasterRow]:
    normalized_exchange = _code(exchange)
    rows: list[NormalizedScriptMasterRow] = []
    seen: set[tuple[str, str]] = set()
    for raw in iter_script_master_rows(response):
        row = normalize_script_master_row(raw, normalized_exchange)
        if row is None:
            continue
        key = (row.exchange, row.scrip_code)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)
    return rows


def iter_script_master_rows(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        for item in payload:
            yield from iter_script_master_rows(item)
        return
    if isinstance(payload, dict):
        if _looks_like_instrument(payload):
            yield _json_ready_dict(payload)
            return
        for key in ("data", "Data", "result", "Result", "records", "Records", "instruments", "Instruments"):
            if key in payload:
                yield from iter_script_master_rows(payload[key])
                return
        for value in payload.values():
            if isinstance(value, (list, dict, str)):
                yield from iter_script_master_rows(value)
        return
    if isinstance(payload, str):
        text = payload.strip()
        if not text:
            return
        parsed = _parse_json_text(text)
        if parsed is not None:
            yield from iter_script_master_rows(parsed)
            return
        yield from _parse_delimited_rows(text)


def normalize_script_master_row(raw: dict[str, Any], fallback_exchange: str) -> NormalizedScriptMasterRow | None:
    exchange = _code(_field(raw, *EXCHANGE_FIELDS) or fallback_exchange)
    scrip_code = _scrip_code_text(_field(raw, *SCRIP_CODE_FIELDS))
    trading_symbol = _symbol(_field(raw, *TRADING_SYMBOL_FIELDS))
    if not exchange or not scrip_code or not trading_symbol:
        return None

    strike_price = _decimal_or_none(_field(raw, *STRIKE_FIELDS))
    if strike_price == Decimal("0"):
        strike_price = None

    return NormalizedScriptMasterRow(
        exchange=exchange,
        segment=_code(_field(raw, *SEGMENT_FIELDS)) or None,
        scrip_code=scrip_code,
        trading_symbol=trading_symbol,
        symbol_name=_symbol(_field(raw, *SYMBOL_NAME_FIELDS)),
        underlying_symbol=_symbol(_field(raw, *UNDERLYING_SYMBOL_FIELDS)),
        instrument_type=_code(_field(raw, *INSTRUMENT_FIELDS)) or None,
        option_type=_option_type(_field(raw, *OPTION_FIELDS)),
        strike_price=strike_price,
        expiry_date=_date_or_none(_field(raw, *EXPIRY_FIELDS)),
        lot_size=_int_or_none(_field(raw, *LOT_SIZE_FIELDS)),
        isin=_code(_field(raw, *ISIN_FIELDS)) or None,
        raw_payload_json=_json_ready_dict(raw),
    )


def match_script_master_records(records: Sequence[Any], lookup: ScriptMasterLookup) -> ScriptMasterResolution:
    lookup = _normalize_lookup(lookup)
    if not records:
        return ScriptMasterResolution(
            status=CACHE_EMPTY,
            message=f"scripCode missing and could not be resolved because Script Master cache for {lookup.exchange} is empty.",
        )
    if not lookup.symbol or not lookup.exchange:
        return ScriptMasterResolution(
            status=UNRESOLVED,
            message="scripCode missing and could not be resolved because the WebSocket event lacks symbol or exchange.",
        )

    candidates = [
        record
        for record in records
        if _record_matches_exchange(record, lookup) and _record_matches_identity(record, lookup)
    ]
    if not candidates:
        return _unresolved(lookup, "no Script Master record matched the event identifiers")

    if _lookup_is_derivative(lookup):
        missing = _missing_derivative_lookup_fields(lookup)
        if missing:
            return _unresolved(lookup, f"derivative event is missing required fields: {', '.join(missing)}")
        candidates = [
            record
            for record in candidates
            if _same_date(_attr(record, "expiry_date"), lookup.expiry_date)
            and _same_decimal(_attr(record, "strike_price"), lookup.strike_price)
            and _same_text(_attr(record, "option_type"), lookup.option_type)
        ]
        if lookup.instrument_type:
            candidates = [record for record in candidates if _same_text(_attr(record, "instrument_type"), lookup.instrument_type)]
        if lookup.lot_size:
            lot_matches = [record for record in candidates if _int_or_none(_attr(record, "lot_size")) == lookup.lot_size]
            candidates = lot_matches or candidates
    else:
        if lookup.isin:
            isin_matches = [record for record in candidates if _same_text(_attr(record, "isin"), lookup.isin)]
            candidates = isin_matches or candidates
        equity_candidates = [record for record in candidates if not _record_is_derivative(record)]
        candidates = equity_candidates or candidates
        if lookup.lot_size:
            lot_matches = [record for record in candidates if _int_or_none(_attr(record, "lot_size")) == lookup.lot_size]
            candidates = lot_matches or candidates

    if not candidates:
        return _unresolved(lookup, "Script Master records existed but none matched the required instrument details")
    return _resolution_from_candidates(candidates, lookup)


class ScriptMasterService:
    def __init__(self, broker_router: BrokerRouterClient | None = None) -> None:
        self.broker_router = broker_router or BrokerRouterClient()

    async def refresh_exchange(self, db: AsyncSession, exchange: str, account_id: uuid.UUID) -> dict[str, Any]:
        exchange = _code(exchange)
        if not exchange:
            raise ValueError("exchange is required")
        logger.info("script_master.fetch_started", extra={"exchange": exchange, "account_id": str(account_id)})
        response = await self.broker_router.master(exchange, account_id)
        rows = normalize_script_master_response(response, exchange)
        refreshed_at = utcnow()
        if not rows:
            logger.warning("script_master.fetch_empty", extra={"exchange": exchange, "account_id": str(account_id)})
            return {"exchange": exchange, "records": 0, "refreshed_at": refreshed_at}

        await db.execute(delete(ScriptMasterInstrument).where(ScriptMasterInstrument.exchange == exchange))
        values = [_row_to_db_values(row, refreshed_at) for row in rows]
        for chunk in _chunks(values, 1000):
            await db.execute(insert(ScriptMasterInstrument), chunk)
        await db.flush()
        logger.info(
            "script_master.fetch_completed",
            extra={"exchange": exchange, "account_id": str(account_id), "records": len(values)},
        )
        return {"exchange": exchange, "records": len(values), "refreshed_at": refreshed_at}

    async def status(self, db: AsyncSession, exchange: str) -> dict[str, Any]:
        exchange = _code(exchange)
        count, refreshed_at = await self._cache_status(db, exchange)
        return {"exchange": exchange, "records": count, "refreshed_at": refreshed_at}

    async def resolve(
        self,
        db: AsyncSession,
        lookup: ScriptMasterLookup,
        account_id: uuid.UUID,
    ) -> ScriptMasterResolution:
        lookup = _normalize_lookup(lookup)
        try:
            refreshed = await self.ensure_exchange_cache(db, lookup.exchange, account_id)
        except Exception as exc:
            logger.exception("script_master.fetch_failed", extra={"exchange": lookup.exchange, "account_id": str(account_id)})
            return ScriptMasterResolution(
                status=CACHE_EMPTY,
                message=f"scripCode missing and could not be resolved because Script Master cache for {lookup.exchange} could not be loaded: {exc}",
            )

        records = await self._load_lookup_records(db, lookup)
        resolution = match_script_master_records(records, lookup)
        resolution = ScriptMasterResolution(
            status=resolution.status,
            message=resolution.message,
            scrip_code=resolution.scrip_code,
            record_id=resolution.record_id,
            candidates=resolution.candidates,
            refreshed=refreshed,
        )
        self._log_resolution(lookup, resolution)
        return resolution

    async def ensure_exchange_cache(self, db: AsyncSession, exchange: str, account_id: uuid.UUID) -> bool:
        exchange = _code(exchange)
        count, refreshed_at = await self._cache_status(db, exchange)
        ttl_hours = max(1, get_settings().script_master_cache_ttl_hours)
        stale_before = utcnow() - timedelta(hours=ttl_hours)
        if count > 0 and refreshed_at and refreshed_at > stale_before:
            logger.info(
                "script_master.cache_loaded",
                extra={"exchange": exchange, "records": count, "refreshed_at": refreshed_at.isoformat()},
            )
            return False
        try:
            await self.refresh_exchange(db, exchange, account_id)
            return True
        except Exception:
            if count > 0:
                logger.warning(
                    "script_master.fetch_failed_using_stale_cache",
                    extra={"exchange": exchange, "records": count, "refreshed_at": refreshed_at.isoformat() if refreshed_at else None},
                    exc_info=True,
                )
                return False
            raise

    async def _cache_status(self, db: AsyncSession, exchange: str) -> tuple[int, datetime | None]:
        result = await db.execute(
            select(func.count(ScriptMasterInstrument.id), func.max(ScriptMasterInstrument.refreshed_at)).where(
                ScriptMasterInstrument.exchange == exchange
            )
        )
        count, refreshed_at = result.one()
        return int(count or 0), refreshed_at

    async def _load_lookup_records(self, db: AsyncSession, lookup: ScriptMasterLookup) -> list[ScriptMasterInstrument]:
        exchange_values = {value for value in (_code(lookup.exchange), _code(lookup.segment)) if value}
        identity_filters = []
        if lookup.symbol:
            identity_filters.extend(
                [
                    ScriptMasterInstrument.trading_symbol == lookup.symbol,
                    ScriptMasterInstrument.underlying_symbol == lookup.symbol,
                    ScriptMasterInstrument.symbol_name == lookup.symbol,
                ]
            )
        if lookup.isin:
            identity_filters.append(ScriptMasterInstrument.isin == lookup.isin)
        if not exchange_values or not identity_filters:
            return []
        statement = (
            select(ScriptMasterInstrument)
            .where(
                or_(
                    ScriptMasterInstrument.exchange.in_(exchange_values),
                    ScriptMasterInstrument.segment.in_(exchange_values),
                ),
                or_(*identity_filters),
            )
            .limit(100)
        )
        records = (await db.scalars(statement)).all()
        return list(records)

    @staticmethod
    def _log_resolution(lookup: ScriptMasterLookup, resolution: ScriptMasterResolution) -> None:
        extra = {
            "symbol": lookup.symbol,
            "exchange": lookup.exchange,
            "status": resolution.status,
            "scrip_code": resolution.scrip_code,
            "candidate_count": len(resolution.candidates),
        }
        if resolution.status == RESOLVED:
            logger.info("script_master.match_success", extra=extra)
        elif resolution.status == AMBIGUOUS:
            logger.warning("script_master.match_ambiguous", extra=extra)
        else:
            logger.warning("script_master.match_failure", extra=extra)


script_master_service = ScriptMasterService()


def _normalize_lookup(lookup: ScriptMasterLookup) -> ScriptMasterLookup:
    strike_price = _decimal_or_none(lookup.strike_price)
    if strike_price == Decimal("0"):
        strike_price = None
    return ScriptMasterLookup(
        symbol=_symbol(lookup.symbol) or "",
        exchange=_code(lookup.exchange),
        segment=_code(lookup.segment) or None,
        instrument_type=_code(lookup.instrument_type) or None,
        option_type=_option_type(lookup.option_type),
        strike_price=strike_price,
        expiry_date=_date_or_none(lookup.expiry_date),
        lot_size=_int_or_none(lookup.lot_size),
        isin=_code(lookup.isin) or None,
    )


def _resolution_from_candidates(candidates: Sequence[Any], lookup: ScriptMasterLookup) -> ScriptMasterResolution:
    unique_by_scrip: dict[int, Any] = {}
    for candidate in candidates:
        scrip_code = _int_or_none(_attr(candidate, "scrip_code"))
        if scrip_code is not None:
            unique_by_scrip[scrip_code] = candidate
    if len(unique_by_scrip) == 1:
        scrip_code, record = next(iter(unique_by_scrip.items()))
        return ScriptMasterResolution(
            status=RESOLVED,
            message=f"scripCode resolved from Script Master for {lookup.symbol} on {lookup.exchange}: {scrip_code}.",
            scrip_code=scrip_code,
            record_id=_attr(record, "id"),
            candidates=(_candidate_payload(record),),
        )
    if len(unique_by_scrip) > 1:
        candidate_payloads = tuple(_candidate_payload(candidate) for candidate in candidates[:10])
        values = ", ".join(str(value) for value in sorted(unique_by_scrip))
        return ScriptMasterResolution(
            status=AMBIGUOUS,
            message=f"multiple Script Master matches found for {lookup.symbol} on {lookup.exchange}: {values}.",
            candidates=candidate_payloads,
        )
    return _unresolved(lookup, "matched Script Master rows do not contain a valid numeric scripCode")


def _unresolved(lookup: ScriptMasterLookup, reason: str) -> ScriptMasterResolution:
    return ScriptMasterResolution(
        status=UNRESOLVED,
        message=f"scripCode missing and could not be resolved from Script Master for {lookup.symbol} on {lookup.exchange}: {reason}.",
    )


def _lookup_is_derivative(lookup: ScriptMasterLookup) -> bool:
    return any((lookup.option_type, lookup.strike_price is not None, lookup.expiry_date, _derivative_instrument(lookup.instrument_type)))


def _missing_derivative_lookup_fields(lookup: ScriptMasterLookup) -> list[str]:
    missing: list[str] = []
    if lookup.expiry_date is None:
        missing.append("expiry")
    if lookup.strike_price is None:
        missing.append("strike_price")
    if lookup.option_type is None:
        missing.append("option_type")
    return missing


def _record_matches_exchange(record: Any, lookup: ScriptMasterLookup) -> bool:
    lookup_values = {value for value in (_code(lookup.exchange), _code(lookup.segment)) if value}
    record_values = {value for value in (_code(_attr(record, "exchange")), _code(_attr(record, "segment"))) if value}
    return bool(lookup_values & record_values)


def _record_matches_identity(record: Any, lookup: ScriptMasterLookup) -> bool:
    if lookup.isin and _same_text(_attr(record, "isin"), lookup.isin):
        return True
    symbols = {
        value
        for value in (
            _symbol(_attr(record, "trading_symbol")),
            _symbol(_attr(record, "underlying_symbol")),
            _symbol(_attr(record, "symbol_name")),
        )
        if value
    }
    return lookup.symbol in symbols


def _record_is_derivative(record: Any) -> bool:
    return any(
        (
            _option_type(_attr(record, "option_type")),
            _decimal_or_none(_attr(record, "strike_price")) not in (None, Decimal("0")),
            _date_or_none(_attr(record, "expiry_date")),
            _derivative_instrument(_attr(record, "instrument_type")),
        )
    )


def _derivative_instrument(value: Any) -> bool:
    instrument = _code(value)
    if not instrument:
        return False
    return instrument not in {"EQ", "EQUITY", "CASH", "STK", "STOCK"}


def _candidate_payload(record: Any) -> dict[str, Any]:
    record_id = _attr(record, "id")
    expiry = _date_or_none(_attr(record, "expiry_date"))
    return {
        "id": str(record_id) if record_id else None,
        "exchange": _attr(record, "exchange"),
        "segment": _attr(record, "segment"),
        "scripCode": _attr(record, "scrip_code"),
        "tradingSymbol": _attr(record, "trading_symbol"),
        "underlyingSymbol": _attr(record, "underlying_symbol"),
        "instrumentType": _attr(record, "instrument_type"),
        "optionType": _attr(record, "option_type"),
        "strikePrice": str(_attr(record, "strike_price")) if _attr(record, "strike_price") is not None else None,
        "expiry": expiry.isoformat() if expiry else None,
        "lotSize": _attr(record, "lot_size"),
        "isin": _attr(record, "isin"),
    }


def _row_to_db_values(row: NormalizedScriptMasterRow, refreshed_at: datetime) -> dict[str, Any]:
    return {
        "id": uuid.uuid4(),
        "exchange": row.exchange,
        "segment": row.segment,
        "scrip_code": row.scrip_code,
        "trading_symbol": row.trading_symbol,
        "symbol_name": row.symbol_name,
        "underlying_symbol": row.underlying_symbol,
        "instrument_type": row.instrument_type,
        "option_type": row.option_type,
        "strike_price": row.strike_price,
        "expiry_date": row.expiry_date,
        "lot_size": row.lot_size,
        "isin": row.isin,
        "raw_payload_json": row.raw_payload_json,
        "refreshed_at": refreshed_at,
        "created_at": refreshed_at,
        "updated_at": refreshed_at,
    }


def _looks_like_instrument(row: dict[str, Any]) -> bool:
    return _field(row, *SCRIP_CODE_FIELDS) not in (None, "") and _field(row, *TRADING_SYMBOL_FIELDS) not in (None, "")


def _parse_json_text(text: str) -> Any | None:
    if not text.startswith(("{", "[")):
        return None
    try:
        return json.loads(text)
    except ValueError:
        return None


def _parse_delimited_rows(text: str) -> Iterable[dict[str, Any]]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",|\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    return (_json_ready_dict(row) for row in reader if any(value not in (None, "") for value in row.values()))


def _field(row: dict[str, Any], *names: str) -> Any:
    normalized = {_key(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_key(name))
        if value not in (None, ""):
            return value
    return None


def _attr(record: Any, name: str) -> Any:
    if isinstance(record, dict):
        return record.get(name)
    return getattr(record, name, None)


def _key(value: Any) -> str:
    return "".join(ch for ch in str(value).lower().strip() if ch.isalnum())


def _code(value: Any) -> str:
    text = _text(value)
    return text.upper() if text else ""


def _symbol(value: Any) -> str | None:
    text = _text(value)
    return text.upper() if text else None


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.upper() in {"NULL", "NONE", "NA", "N/A", "-"}:
        return None
    return text


def _scrip_code_text(value: Any) -> str | None:
    number = _int_or_none(value)
    if number is not None:
        return str(number)
    return _text(value)


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(Decimal(str(value).replace(",", "")))
    except (InvalidOperation, ValueError):
        return None


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.0001"))
    except (InvalidOperation, ValueError):
        return None


def _date_or_none(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    candidates = [text, text.split("T", 1)[0]]
    if " " in text and not any(ch.isalpha() for ch in text):
        candidates.append(text.split(" ", 1)[0])
    for candidate in dict.fromkeys(candidates):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d-%b-%Y", "%d %b %Y", "%d%b%Y", "%Y%m%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    return None


def _option_type(value: Any) -> str | None:
    option = _code(value)
    if not option:
        return None
    if option in {"CALL", "C"}:
        return "CE"
    if option in {"PUT", "P"}:
        return "PE"
    return option


def _same_text(left: Any, right: Any) -> bool:
    return _code(left) == _code(right)


def _same_decimal(left: Any, right: Any) -> bool:
    return _decimal_or_none(left) == _decimal_or_none(right)


def _same_date(left: Any, right: Any) -> bool:
    return _date_or_none(left) == _date_or_none(right)


def _json_ready_dict(row: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in row.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            output[str(key)] = value
        elif isinstance(value, (Decimal, datetime, date)):
            output[str(key)] = str(value)
        else:
            output[str(key)] = value
    return output


def _chunks(values: Sequence[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for index in range(0, len(values), size):
        yield list(values[index : index + size])
