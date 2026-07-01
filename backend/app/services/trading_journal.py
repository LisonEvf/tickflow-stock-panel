"""Manual trading journal and derived portfolio state.

The trading page is a manual reconciliation surface for a real brokerage
account.  We persist the small editable journal under user_data and derive cash,
positions and PnL from that journal on every read.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

TradeSide = Literal["buy", "sell"]

_lock = threading.Lock()

DEFAULT_FEE_SETTINGS = {
    "commission_rate": 0.00025,
    "min_commission": 5.0,
    "stamp_tax_rate": 0.0005,
    "transfer_fee_rate": 0.00001,
}

DEFAULT_ACCOUNT = {
    "principal": 100000.0,
    "cash_adjustment": 0.0,
    "fee_settings": DEFAULT_FEE_SETTINGS,
}


def _path(data_dir: Path) -> Path:
    p = data_dir / "user_data" / "trading_journal.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        f = float(value)
        if math.isfinite(f):
            return f
    except (TypeError, ValueError):
        pass
    return default


def _safe_int(value: object, default: int = 0) -> int:
    try:
        i = int(value)
        return i if i >= 0 else default
    except (TypeError, ValueError):
        return default


def _normalize_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _normalize_fee_settings(raw: dict | None) -> dict:
    raw = raw or {}
    out = dict(DEFAULT_FEE_SETTINGS)
    for key in out:
        out[key] = max(0.0, _safe_float(raw.get(key), out[key]))
    return out


def _empty_journal() -> dict:
    account = deepcopy(DEFAULT_ACCOUNT)
    return {
        "version": 1,
        "account": {
            **account,
            "fee_settings": dict(DEFAULT_FEE_SETTINGS),
            "updated_at": _now_iso(),
        },
        "trades": [],
    }


def load_journal(data_dir: Path) -> dict:
    """Load and normalize the persisted journal."""
    p = _path(data_dir)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.warning("trading_journal.json malformed: %s", e)
            data = {}
    else:
        data = {}

    journal = _empty_journal()
    account = data.get("account") if isinstance(data, dict) else {}
    if isinstance(account, dict):
        journal["account"].update({
            "principal": max(0.0, _safe_float(account.get("principal"), DEFAULT_ACCOUNT["principal"])),
            "cash_adjustment": _safe_float(account.get("cash_adjustment"), 0.0),
            "fee_settings": _normalize_fee_settings(account.get("fee_settings")),
            "updated_at": str(account.get("updated_at") or journal["account"]["updated_at"]),
        })

    trades = data.get("trades") if isinstance(data, dict) else []
    if isinstance(trades, list):
        journal["trades"] = [_normalize_trade(t, journal["account"]["fee_settings"]) for t in trades if isinstance(t, dict)]
    return journal


def _write_journal(data_dir: Path, journal: dict) -> None:
    _path(data_dir).write_text(
        json.dumps(journal, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def calculate_fee(
    side: TradeSide,
    price: float,
    quantity: int,
    fee_settings: dict | None = None,
) -> float:
    """Calculate A-share style total fee for one manual trade."""
    settings = _normalize_fee_settings(fee_settings)
    amount = max(0.0, float(price) * int(quantity))
    if amount <= 0:
        return 0.0
    commission = max(amount * settings["commission_rate"], settings["min_commission"])
    stamp_tax = amount * settings["stamp_tax_rate"] if side == "sell" else 0.0
    transfer_fee = amount * settings["transfer_fee_rate"]
    return round(commission + stamp_tax + transfer_fee, 4)


def _normalize_trade(raw: dict, fee_settings: dict | None = None) -> dict:
    side = "sell" if raw.get("side") == "sell" else "buy"
    price = max(0.0, _safe_float(raw.get("price"), 0.0))
    quantity = _safe_int(raw.get("quantity"), 0)
    fee = raw.get("fee")
    fee_value = calculate_fee(side, price, quantity, fee_settings) if fee is None else max(0.0, _safe_float(fee))
    created_at = str(raw.get("created_at") or _now_iso())
    updated_at = str(raw.get("updated_at") or created_at)
    return {
        "id": str(raw.get("id") or f"tr_{int(time.time() * 1000)}"),
        "symbol": _normalize_symbol(str(raw.get("symbol") or "")),
        "name": str(raw.get("name") or "").strip(),
        "side": side,
        "trade_time": str(raw.get("trade_time") or _now_iso()),
        "price": round(price, 4),
        "quantity": quantity,
        "fee": round(fee_value, 4),
        "note": str(raw.get("note") or "").strip(),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def update_account(data_dir: Path, updates: dict) -> dict:
    """Update principal/cash adjustment/fee settings and persist."""
    with _lock:
        journal = load_journal(data_dir)
        account = dict(journal["account"])
        if "principal" in updates and updates["principal"] is not None:
            account["principal"] = max(0.0, _safe_float(updates["principal"], account["principal"]))
        if "cash_adjustment" in updates and updates["cash_adjustment"] is not None:
            account["cash_adjustment"] = _safe_float(updates["cash_adjustment"], account["cash_adjustment"])
        if "fee_settings" in updates and updates["fee_settings"] is not None:
            merged = dict(account.get("fee_settings") or DEFAULT_FEE_SETTINGS)
            merged.update(updates["fee_settings"])
            account["fee_settings"] = _normalize_fee_settings(merged)
        account["updated_at"] = _now_iso()
        journal["account"] = account
        _write_journal(data_dir, journal)
        return account


def list_trades(data_dir: Path) -> list[dict]:
    return sorted(
        load_journal(data_dir)["trades"],
        key=lambda r: (str(r.get("trade_time") or ""), str(r.get("created_at") or "")),
        reverse=True,
    )


def add_trade(data_dir: Path, payload: dict) -> dict:
    with _lock:
        journal = load_journal(data_dir)
        trade = _normalize_trade(
            {**payload, "id": payload.get("id") or f"tr_{int(time.time() * 1000)}"},
            journal["account"]["fee_settings"],
        )
        _validate_trade(trade)
        journal["trades"].append(trade)
        _ensure_no_negative_position(journal)
        _write_journal(data_dir, journal)
        return trade


def update_trade(data_dir: Path, trade_id: str, updates: dict) -> dict | None:
    with _lock:
        journal = load_journal(data_dir)
        idx = next((i for i, t in enumerate(journal["trades"]) if t.get("id") == trade_id), -1)
        if idx < 0:
            return None
        existing = journal["trades"][idx]
        raw = {**existing, **updates, "id": trade_id, "created_at": existing.get("created_at"), "updated_at": _now_iso()}
        trade = _normalize_trade(raw, journal["account"]["fee_settings"])
        _validate_trade(trade)
        journal["trades"][idx] = trade
        _ensure_no_negative_position(journal)
        _write_journal(data_dir, journal)
        return trade


def delete_trade(data_dir: Path, trade_id: str) -> bool:
    with _lock:
        journal = load_journal(data_dir)
        before = len(journal["trades"])
        journal["trades"] = [t for t in journal["trades"] if t.get("id") != trade_id]
        if len(journal["trades"]) == before:
            return False
        _ensure_no_negative_position(journal)
        _write_journal(data_dir, journal)
        return True


def _validate_trade(trade: dict) -> None:
    if not trade.get("symbol"):
        raise ValueError("symbol is required")
    if trade.get("price", 0) <= 0:
        raise ValueError("price must be positive")
    if trade.get("quantity", 0) <= 0:
        raise ValueError("quantity must be positive")


def _sorted_trades(trades: list[dict]) -> list[dict]:
    return sorted(trades, key=lambda r: (str(r.get("trade_time") or ""), str(r.get("created_at") or ""), str(r.get("id") or "")))


def _derive_positions(journal: dict) -> tuple[dict[str, dict], float, float, list[str]]:
    positions: dict[str, dict] = {}
    realized_total = 0.0
    cash_delta = 0.0
    warnings: list[str] = []

    for trade in _sorted_trades(journal.get("trades", [])):
        symbol = trade["symbol"]
        amount = float(trade["price"]) * int(trade["quantity"])
        fee = float(trade.get("fee") or 0)
        pos = positions.setdefault(symbol, {
            "symbol": symbol,
            "name": trade.get("name") or "",
            "quantity": 0,
            "cost_basis": 0.0,
            "realized_pnl": 0.0,
        })
        if trade.get("name"):
            pos["name"] = trade["name"]

        if trade["side"] == "buy":
            pos["quantity"] += int(trade["quantity"])
            pos["cost_basis"] += amount + fee
            cash_delta -= amount + fee
            continue

        qty = int(trade["quantity"])
        if qty > pos["quantity"]:
            warnings.append(f"{symbol} 卖出数量超过当前持仓")
            avg_cost = pos["cost_basis"] / pos["quantity"] if pos["quantity"] else 0.0
            qty = pos["quantity"]
        else:
            avg_cost = pos["cost_basis"] / pos["quantity"] if pos["quantity"] else 0.0

        realized = amount - fee - avg_cost * qty
        pos["quantity"] -= qty
        pos["cost_basis"] -= avg_cost * qty
        if pos["quantity"] <= 0:
            pos["quantity"] = 0
            pos["cost_basis"] = 0.0
        pos["realized_pnl"] += realized
        realized_total += realized
        cash_delta += amount - fee

    return positions, realized_total, cash_delta, warnings


def _ensure_no_negative_position(journal: dict) -> None:
    positions, _realized, _cash_delta, warnings = _derive_positions(journal)
    if warnings:
        raise ValueError(warnings[0])
    for symbol, pos in positions.items():
        if int(pos.get("quantity") or 0) < 0:
            raise ValueError(f"{symbol} 持仓不能为负")


def build_portfolio(
    data_dir: Path,
    *,
    price_map: dict[str, float | None] | None = None,
    name_map: dict[str, str | None] | None = None,
) -> dict:
    """Return account, trades, current positions and account summary."""
    journal = load_journal(data_dir)
    account = journal["account"]
    positions_raw, realized_total, cash_delta, warnings = _derive_positions(journal)
    price_map = price_map or {}
    name_map = name_map or {}

    positions: list[dict] = []
    market_value_total = 0.0
    unrealized_total = 0.0
    for symbol, pos in sorted(positions_raw.items()):
        quantity = int(pos.get("quantity") or 0)
        if quantity <= 0:
            continue
        avg_cost = float(pos["cost_basis"]) / quantity if quantity else 0.0
        latest_price = price_map.get(symbol)
        valuation_price = _safe_float(latest_price, avg_cost) if latest_price is not None else avg_cost
        market_value = valuation_price * quantity
        unrealized = (valuation_price - avg_cost) * quantity
        market_value_total += market_value
        unrealized_total += unrealized
        positions.append({
            "symbol": symbol,
            "name": name_map.get(symbol) or pos.get("name") or "",
            "quantity": quantity,
            "avg_cost": round(avg_cost, 4),
            "cost_basis": round(float(pos["cost_basis"]), 4),
            "latest_price": round(float(latest_price), 4) if latest_price is not None else None,
            "market_value": round(market_value, 4),
            "unrealized_pnl": round(unrealized, 4),
            "unrealized_pnl_pct": round(unrealized / float(pos["cost_basis"]), 6) if pos["cost_basis"] else None,
            "realized_pnl": round(float(pos.get("realized_pnl") or 0), 4),
        })

    principal = float(account.get("principal") or 0)
    cash_adjustment = float(account.get("cash_adjustment") or 0)
    cash = principal + cash_adjustment + cash_delta
    total_assets = cash + market_value_total
    for pos in positions:
        pos["weight"] = round(pos["market_value"] / total_assets, 6) if total_assets else 0.0

    summary = {
        "principal": round(principal, 4),
        "cash_adjustment": round(cash_adjustment, 4),
        "cash": round(cash, 4),
        "market_value": round(market_value_total, 4),
        "total_assets": round(total_assets, 4),
        "realized_pnl": round(realized_total, 4),
        "unrealized_pnl": round(unrealized_total, 4),
        "total_pnl": round(realized_total + unrealized_total, 4),
        "position_ratio": round(market_value_total / total_assets, 6) if total_assets else 0.0,
    }
    return {
        "account": account,
        "summary": summary,
        "positions": positions,
        "trades": list_trades(data_dir),
        "warnings": warnings,
    }


def portfolio_context_for_symbol(
    data_dir: Path,
    symbol: str,
    latest_price: float | None = None,
) -> dict:
    """Small, stable context block for AI stock analysis prompts."""
    normalized_symbol = _normalize_symbol(symbol)
    price_map = {normalized_symbol: latest_price} if latest_price is not None else {}
    portfolio = build_portfolio(data_dir, price_map=price_map)
    position = next((p for p in portfolio["positions"] if p["symbol"] == normalized_symbol), None)
    summary = portfolio["summary"]
    return {
        "symbol": normalized_symbol,
        "held": bool(position),
        "position": position,
        "account": {
            "cash": summary["cash"],
            "market_value": summary["market_value"],
            "total_assets": summary["total_assets"],
            "position_ratio": summary["position_ratio"],
            "realized_pnl": summary["realized_pnl"],
            "unrealized_pnl": summary["unrealized_pnl"],
        },
    }
