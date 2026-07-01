"""Realtime plate rank fallback from the public Kaipanla-compatible API.

The local project already treats OpenTDX as the primary quote source. This
module is intentionally narrow: it only fetches concept/industry plate ranks
for dashboard cards when local extension data is missing.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_URL = "https://apphwhq.kaipanhong.com/w1/api/index.php"
_UA = "kaipanhong/6.0.10 Android/11 okhttp/4.12.0"
_DEVICE_ID = "5605b900-4e2d-3ee2-a044-10ac82aada73"
_CACHE_TTL_SECONDS = 45.0
_KIND_TO_ZS_TYPE = {"concept": 7, "industry": 4}

_cache: dict[str, tuple[float, dict[str, list[dict[str, Any]]]]] = {}


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _rank_item(row: list[Any]) -> dict[str, Any] | None:
    if len(row) < 4:
        return None
    name = str(row[1] or "").strip()
    pct = _finite_number(row[3])
    if not name or pct is None:
        return None

    strength = _finite_number(row[2])
    turnover = _finite_number(row[5] if len(row) > 5 else None) or 0.0
    main_net = _finite_number(row[6] if len(row) > 6 else None)
    metric_parts = []
    if strength is not None:
        metric_parts.append(f"strength {strength:.0f}")
    if main_net is not None:
        metric_parts.append(f"net {main_net:.0f}")

    return {
        "name": name,
        "count": 0,
        "avg_pct": pct / 100.0,
        "up_count": 0,
        "down_count": 0,
        "amount": turnover,
        "leader": None,
        "source": "openkpl",
        "plate_id": str(row[0] or ""),
        "metric_label": " / ".join(metric_parts),
    }


def _items_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for row in payload.get("list") or []
        if isinstance(row, list)
        for item in [_rank_item(row)]
        if item is not None
    ]


def rank_from_payload(payload: dict[str, Any], limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    """Convert raw RealRankingInfo JSON into the overview rank shape."""
    items = _items_from_payload(payload)
    leading = sorted(items, key=lambda item: item["avg_pct"], reverse=True)[:limit]
    lagging = sorted(items, key=lambda item: item["avg_pct"])[:limit]
    return {"leading": leading, "lagging": lagging}


def _fetch_payload(kind: str, order: str, count: int) -> dict[str, Any]:
    zs_type = _KIND_TO_ZS_TYPE[kind]
    params = {
        "apiv": "w45",
        "PhoneOSNew": "1",
        "VerSion": "6.0.10",
        "Red": "1",
    }
    form = {
        **params,
        "Order": order,
        "a": "RealRankingInfo",
        "st": str(count),
        "c": "ZhiShuRanking",
        "Index": "0",
        "Type": "1",
        "ZSType": str(zs_type),
        "DeviceID": _DEVICE_ID,
    }
    headers = {
        "User-Agent": _UA,
        "X-Requested-With": "com.yzj.kaipanh",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    with httpx.Client(timeout=5.0, headers=headers) as client:
        response = client.post(_URL, params=params, data=form)
        response.raise_for_status()
        payload = response.json()
    errcode = payload.get("errcode")
    if errcode not in (None, 0, "0"):
        raise RuntimeError(f"openkpl rank API error: {errcode}")
    return payload


def _fetch_rank(kind: str, limit: int) -> dict[str, list[dict[str, Any]]]:
    count = 320 if kind == "concept" else 140
    payload = _fetch_payload(kind, order="1", count=count)
    leading = sorted(_items_from_payload(payload), key=lambda item: item["avg_pct"], reverse=True)[:limit]
    return {"leading": leading, "lagging": []}


def get_realtime_rank(kind: str, limit: int = 5) -> dict[str, list[dict[str, Any]]]:
    """Return cached realtime concept/industry rank, or empty rank on failure."""
    if kind not in _KIND_TO_ZS_TYPE:
        raise ValueError(f"unsupported openkpl rank kind: {kind}")

    now = time.monotonic()
    cached = _cache.get(kind)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    try:
        rank = _fetch_rank(kind, limit)
    except Exception as exc:  # noqa: BLE001
        logger.warning("openkpl realtime %s rank fetch failed: %s", kind, exc)
        return {"leading": [], "lagging": []}

    _cache[kind] = (now, rank)
    return rank


def clear_cache() -> None:
    _cache.clear()
