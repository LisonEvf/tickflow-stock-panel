"""OpenKPL/OpenKPH realtime data adapters for focused market pages."""
from __future__ import annotations

import logging
import math
import re
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

logger = logging.getLogger(__name__)

_OPENKPH_SRC = Path(__file__).resolve().parents[2] / "openkph" / "src"
_CACHE_TTL_SECONDS = 45.0
_DEFAULT_RANK_LIMIT = 36
_DEFAULT_STOCKS_PER_PLATE = 80

_client: Any | None = None
_client_lock = RLock()
_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _ensure_openkph_path() -> None:
    path = str(_OPENKPH_SRC)
    if path not in sys.path:
        sys.path.insert(0, path)


def _openkph_symbols() -> tuple[Any, Any, Any, Any]:
    _ensure_openkph_path()
    from openkph import DaBanType, KPHClient, PlateCategory, SortOrder

    return KPHClient, DaBanType, PlateCategory, SortOrder


def _get_client() -> Any:
    global _client
    KPHClient, _, _, _ = _openkph_symbols()
    if _client is None or not _client.is_connected():
        _client = KPHClient(connect_socket=True, timeout=15)
    return _client


def _reset_client() -> None:
    global _client
    if _client is not None:
        try:
            _client.close()
        except Exception:  # noqa: BLE001
            pass
    _client = None


def _client_call(fn: Callable[[Any], Any]) -> Any:
    with _client_lock:
        client = _get_client()
        try:
            return fn(client)
        except Exception:
            _reset_client()
            client = _get_client()
            return fn(client)


def _cache_get(key: tuple[Any, ...]) -> dict[str, Any] | None:
    cached = _cache.get(key)
    if not cached:
        return None
    ts, payload = cached
    if time.monotonic() - ts >= _CACHE_TTL_SECONDS:
        _cache.pop(key, None)
        return None
    return payload


def _cache_set(key: tuple[Any, ...], payload: dict[str, Any]) -> dict[str, Any]:
    _cache[key] = (time.monotonic(), payload)
    return payload


def clear_cache() -> None:
    _cache.clear()


def _date_arg(as_of: date | str | None) -> str | None:
    if as_of is None:
        return None
    return as_of.isoformat() if isinstance(as_of, date) else str(as_of)


def _today_cn() -> str:
    return datetime.now(timezone(timedelta(hours=8))).date().isoformat()


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _int(value: Any) -> int:
    number = _num(value)
    return int(number) if number is not None else 0


def _pct(value: Any) -> float | None:
    number = _num(value)
    return number / 100.0 if number is not None else None


def _clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


_CN_NUM = {
    "首": 1,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _boards_from_text(text: Any) -> int:
    value = str(text or "").strip()
    match = re.search(r"(\d+)", value)
    if match:
        return max(1, int(match.group(1)))
    for char, number in _CN_NUM.items():
        if char in value:
            return number
    return 1


def _stock_name(stock: Any) -> str:
    return str(getattr(stock, "name", "") or "").strip()


def _stock_symbol(stock: Any) -> str:
    return str(getattr(stock, "stock_id", "") or "").strip()


def _daban_row(stock: Any, status: str, fallback_boards: int, is_down: bool) -> dict[str, Any] | None:
    symbol = _stock_symbol(stock)
    if not symbol:
        return None
    boards = _boards_from_text(getattr(stock, "status", "")) or fallback_boards
    change_pct = _pct(getattr(stock, "change", None))
    price = _num(getattr(stock, "price", None))
    if price == 0:
        price = None
    seal_amount = _num(getattr(stock, "seal", None))
    row = {
        "symbol": symbol,
        "name": _stock_name(stock),
        "close": price,
        "change_pct": change_pct,
        "boards": boards,
        "status": status,
        "consecutive_limit_ups": 0 if is_down else boards,
        "consecutive_limit_downs": boards if is_down else 0,
        "sealed_status": "real" if status in ("limit_up", "limit_down") and seal_amount and seal_amount > 0 else None,
        "sealed_vol": None,
        "sealed_amount": seal_amount,
        "openkpl__concept": str(getattr(stock, "plate", "") or ""),
        "openkpl__industry": "",
        "reason": str(getattr(stock, "reason", "") or ""),
        "zt_time": str(getattr(stock, "zt_time", "") or ""),
        "open_time": str(getattr(stock, "open_time", "") or ""),
        "amount": _num(getattr(stock, "turnover", None)),
        "turnover_rate": _num(getattr(stock, "turnover_ratio", None)),
        "float_market_cap": _num(getattr(stock, "circ", None)),
        "source": "openkpl",
    }
    return _clean(row)


def _group_tiers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tiers: dict[int, list[dict[str, Any]]] = {}
    for row in rows:
        boards = int(row.get("boards") or 1)
        tiers.setdefault(boards, []).append(row)
    return [
        {"boards": boards, "count": len(stocks), "stocks": stocks}
        for boards, stocks in sorted(tiers.items(), key=lambda item: -item[0])
    ]


def get_limit_ladder(
    as_of: date | str | None = None,
    direction: str = "up",
    count: int = 500,
) -> dict[str, Any]:
    """Return the limit-up/down ladder directly from OpenKPL/OpenKPH."""
    is_down = direction == "down"
    date_value = _date_arg(as_of)
    cache_key = ("limit_ladder", date_value or "latest", "down" if is_down else "up", count)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    _, DaBanType, _, _ = _openkph_symbols()

    def _fetch(client: Any) -> tuple[str, list[Any], list[Any], list[Any], list[Any]]:
        zt_date, zt_rows = client.get_daban_list(DaBanType.ZT, date=date_value, count=count)
        _, broken_rows = client.get_daban_list(DaBanType.BROKEN_ZT, date=date_value, count=count)
        dt_date, dt_rows = client.get_daban_list(DaBanType.DT, date=date_value, count=count)
        _, ever_dt_rows = client.get_daban_list(DaBanType.EVER_DT, date=date_value, count=count)
        return zt_date or dt_date or date_value or "", zt_rows, broken_rows, dt_rows, ever_dt_rows

    try:
        data_date, zt_rows, broken_rows, dt_rows, ever_dt_rows = _client_call(_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.warning("openkpl limit ladder fetch failed: %s", exc)
        return {"as_of": date_value, "source": "openkpl", "tiers": [], "counts": {"up": 0, "down": 0}}

    rows: list[dict[str, Any]] = []
    if is_down:
        rows.extend(
            row for stock in dt_rows
            if (row := _daban_row(stock, "limit_down", 1, is_down=True)) is not None
        )
        rows.extend(
            row for stock in ever_dt_rows
            if (row := _daban_row(stock, "recovery", 1, is_down=True)) is not None
        )
    else:
        rows.extend(
            row for stock in zt_rows
            if (row := _daban_row(stock, "limit_up", 1, is_down=False)) is not None
        )
        rows.extend(
            row for stock in broken_rows
            if (row := _daban_row(stock, "broken", 1, is_down=False)) is not None
        )

    status_order = {
        "limit_up": 0,
        "limit_down": 0,
        "broken": 1,
        "recovery": 1,
        "failed": 2,
    }
    rows.sort(key=lambda row: (-(int(row.get("boards") or 0)), status_order.get(str(row.get("status")), 9), str(row.get("symbol") or "")))
    up_count = len(zt_rows)
    down_count = len(dt_rows)
    payload = {
        "as_of": data_date or date_value,
        "source": "openkpl",
        "tiers": _group_tiers(rows),
        "counts": {"up": up_count, "down": down_count},
        "counts_raw": {"up": up_count, "down": down_count},
        "sealed_ready": False,
        "sealed_age": None,
        "sealed_counts": {"real": 0, "fake": 0, "pending": 0},
        "sealed_counts_up": {"real": up_count, "fake": 0, "pending": 0},
        "sealed_counts_down": {"real": down_count, "fake": 0, "pending": 0},
    }
    return _cache_set(cache_key, _clean(payload))


def _rank_item(item: Any) -> dict[str, Any]:
    return _clean({
        "plate_id": str(getattr(item, "plate_id", "") or ""),
        "name": str(getattr(item, "name", "") or ""),
        "strength": _num(getattr(item, "strength", None)),
        "change_pct": _pct(getattr(item, "rise", None)),
        "speed": _pct(getattr(item, "speed", None)),
        "amount": _num(getattr(item, "turnover", None)),
        "net_amount": _num(getattr(item, "net_amount", None)),
        "volume_ratio": _num(getattr(item, "volume_ratio", None)),
        "float_market_cap": _num(getattr(item, "circ_mv", None)),
        "source": "openkpl",
    })


def _fallback_rank(kind: str, limit: int) -> list[dict[str, Any]]:
    try:
        from app.services.openkpl_rank import get_realtime_rank

        return [
            {
                "plate_id": item.get("plate_id"),
                "name": item.get("name"),
                "strength": None,
                "change_pct": item.get("avg_pct"),
                "speed": None,
                "amount": item.get("amount"),
                "net_amount": None,
                "volume_ratio": None,
                "float_market_cap": None,
                "source": "openkpl",
            }
            for item in get_realtime_rank(kind, limit).get("leading", [])
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("openkpl fallback rank fetch failed: %s", exc)
        return []


def _fetch_rank(kind: str, order: Any, limit: int, date_value: str | None) -> tuple[str, int, list[dict[str, Any]]]:
    _, _, PlateCategory, _ = _openkph_symbols()
    category = PlateCategory.CONCEPT if kind == "concept" else PlateCategory.INDUSTRY

    def _fetch(client: Any) -> tuple[str, int, list[Any]]:
        return client.get_plate_ranking(category, order=order, count=limit, date=date_value)

    try:
        data_date, total, rows = _client_call(_fetch)
        return data_date or date_value or "", int(total or len(rows)), [_rank_item(row) for row in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("openkpl %s rank fetch failed: %s", kind, exc)
        if date_value:
            return date_value, 0, []
        fallback = _fallback_rank(kind, limit)
        return "", len(fallback), fallback


def _plate_stock_row(stock: Any, plate: dict[str, Any], field_name: str) -> dict[str, Any] | None:
    symbol = _stock_symbol(stock)
    if not symbol:
        return None
    board_desc = str(getattr(stock, "board_desc", "") or "")
    row = {
        "symbol": symbol,
        "code": symbol,
        "name": _stock_name(stock),
        field_name: plate.get("name") or "",
        "plate_id": plate.get("plate_id"),
        "plate_name": plate.get("name"),
        "plate_strength": plate.get("strength"),
        "plate_change_pct": plate.get("change_pct"),
        "source": "openkpl",
        "close": _num(getattr(stock, "price", None)),
        "change_pct": _pct(getattr(stock, "rise", None)),
        "amount": _num(getattr(stock, "turnover", None)),
        "turnover_rate": _num(getattr(stock, "turnover_rate", None)) or _num(getattr(stock, "real_turnover_rate", None)),
        "vol_ratio_5d": _num(getattr(stock, "volume_ratio", None)),
        "market_cap": _num(getattr(stock, "total_mv", None)),
        "float_market_cap": _num(getattr(stock, "circ_mv", None)) or _num(getattr(stock, "real_circ", None)),
        "consecutive_limit_ups": _boards_from_text(board_desc) if board_desc else 0,
        "leader_tag": str(getattr(stock, "tag", "") or ""),
        "board_desc": board_desc,
        "main_net": _num(getattr(stock, "main_net", None)),
        "main_buy": _num(getattr(stock, "main_buy", None)),
        "main_sell": _num(getattr(stock, "main_sell", None)),
        "strength": _num(getattr(stock, "strength", None)),
    }
    return _clean(row)


def _fetch_plate_stocks(plate: dict[str, Any], field_name: str, count: int, date_value: str | None) -> list[dict[str, Any]]:
    plate_id = str(plate.get("plate_id") or "")
    if not plate_id:
        return []

    def _fetch(client: Any) -> tuple[str, int, list[Any]]:
        try:
            return client.get_plate_stocks(plate_id, count=count, date=date_value)
        except Exception:
            return client.get_plate_stocks_history(plate_id, count=count, date=date_value)

    try:
        _, _, rows = _client_call(_fetch)
    except Exception as exc:  # noqa: BLE001
        logger.debug("openkpl plate stocks fetch skipped for %s: %s", plate_id, exc)
        return []
    return [
        row for stock in rows
        if (row := _plate_stock_row(stock, plate, field_name)) is not None
    ]


def _analysis_fields(field_name: str, field_label: str) -> list[dict[str, str]]:
    return [
        {"name": "symbol", "dtype": "string", "label": "symbol"},
        {"name": "code", "dtype": "string", "label": "code"},
        {"name": "name", "dtype": "string", "label": "name"},
        {"name": field_name, "dtype": "string", "label": field_label},
        {"name": "plate_id", "dtype": "string", "label": "plate_id"},
        {"name": "close", "dtype": "float", "label": "close"},
        {"name": "change_pct", "dtype": "float", "label": "change_pct"},
        {"name": "amount", "dtype": "float", "label": "amount"},
        {"name": "turnover_rate", "dtype": "float", "label": "turnover_rate"},
        {"name": "vol_ratio_5d", "dtype": "float", "label": "vol_ratio_5d"},
        {"name": "market_cap", "dtype": "float", "label": "market_cap"},
        {"name": "float_market_cap", "dtype": "float", "label": "float_market_cap"},
        {"name": "consecutive_limit_ups", "dtype": "int", "label": "consecutive_limit_ups"},
    ]


def get_plate_analysis(
    kind: str,
    rank_limit: int = _DEFAULT_RANK_LIMIT,
    stocks_per_plate: int = _DEFAULT_STOCKS_PER_PLATE,
    as_of: date | str | None = None,
) -> dict[str, Any]:
    """Return concept/industry rows backed only by OpenKPL/OpenKPH."""
    if kind not in {"concept", "industry"}:
        raise ValueError(f"unsupported openkpl plate kind: {kind}")

    date_value = _date_arg(as_of)
    rank_limit = max(1, min(int(rank_limit), 80))
    stocks_per_plate = max(1, min(int(stocks_per_plate), 200))
    cache_key = ("plate_analysis", kind, date_value or "latest", rank_limit, stocks_per_plate)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    _, _, _, SortOrder = _openkph_symbols()
    leading_date, leading_total, leading = _fetch_rank(kind, SortOrder.ASC, rank_limit, date_value)
    lagging_date, lagging_total, lagging = _fetch_rank(kind, SortOrder.DESC, rank_limit, date_value)

    plates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for plate in [*leading, *lagging]:
        plate_id = str(plate.get("plate_id") or "")
        if not plate_id or plate_id in seen:
            continue
        seen.add(plate_id)
        plates.append(plate)

    field_name = "concept" if kind == "concept" else "industry"
    field_label = "concept" if kind == "concept" else "industry"
    rows: list[dict[str, Any]] = []
    plate_summaries: list[dict[str, Any]] = []
    for plate in plates:
        stock_rows = _fetch_plate_stocks(plate, field_name, stocks_per_plate, date_value)
        rows.extend(stock_rows)
        plate_summaries.append({**plate, "stock_count": len(stock_rows)})

    data_date = leading_date or lagging_date or date_value or _today_cn()
    fields = _analysis_fields(field_name, field_label)
    payload = {
        "id": f"openkpl_{kind}",
        "label": f"openkpl_{kind}",
        "mode": "snapshot",
        "date": data_date,
        "as_of": data_date,
        "source": "openkpl",
        "kind": kind,
        "total": len(rows),
        "limit": len(rows),
        "rank_total": max(leading_total, lagging_total),
        "fields": fields,
        "rows": rows,
        "plates": plate_summaries,
    }
    return _cache_set(cache_key, _clean(payload))
