"""OpenTDX-backed capability policy.

The application still imports ``app.tickflow`` in many places.  During the
OpenTDX migration this module keeps that contract stable while reporting the
local OpenTDX data abilities instead of probing TickFlow accounts.
"""
from __future__ import annotations

import json
from typing import Any

from app.config import settings

from .capabilities import Cap, CapabilityLimits, CapabilitySet

_CAPSET_CACHE_FILE = "capabilities.json"
_LABEL = "OpenTDX"


def _opentdx_capset() -> CapabilitySet:
    return CapabilitySet({
        Cap.QUOTE_BY_SYMBOL: CapabilityLimits(rpm=120, batch=80),
        Cap.QUOTE_BATCH: CapabilityLimits(rpm=60, batch=80),
        Cap.QUOTE_POOL: CapabilityLimits(rpm=12, batch=5000),
        Cap.KLINE_DAILY_BY_SYMBOL: CapabilityLimits(rpm=120, batch=1),
        Cap.KLINE_DAILY_BATCH: CapabilityLimits(rpm=60, batch=80),
        Cap.KLINE_MINUTE_BY_SYMBOL: CapabilityLimits(rpm=120, batch=1),
        Cap.KLINE_MINUTE_BATCH: CapabilityLimits(rpm=60, batch=80),
        Cap.INTRADAY: CapabilityLimits(rpm=120, batch=1),
        Cap.INTRADAY_BATCH: CapabilityLimits(rpm=60, batch=80),
        Cap.DEPTH5: CapabilityLimits(rpm=120, batch=1),
        Cap.DEPTH5_BATCH: CapabilityLimits(rpm=60, batch=80),
        Cap.FINANCIAL: CapabilityLimits(rpm=30, batch=50),
    })


def _persist(capset: CapabilitySet) -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema_version": "opentdx-1",
        "label": _LABEL,
        "capabilities": capset.to_dict(),
        "probe_log": ["OpenTDX local provider enabled"],
        "missing_caps": [],
        "extras_caps": [],
        "invalid_key": False,
    }
    (settings.data_dir / _CAPSET_CACHE_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def detect_capabilities(force: bool = False) -> CapabilitySet:  # noqa: ARG001
    capset = _opentdx_capset()
    _persist(capset)
    return capset


def tier_label() -> str:
    return _LABEL


def probe_log() -> list[str]:
    return ["OpenTDX local provider enabled"]


def missing_caps() -> list[str]:
    return []


def extras_caps() -> list[str]:
    return []


def is_invalid_key() -> bool:
    return False


def base_tier_name() -> str:
    return "opentdx"
