"""Manual trading journal API."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

import polars as pl
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.services import trading_journal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trading", tags=["trading"])


class FeeSettingsRequest(BaseModel):
    commission_rate: float | None = Field(default=None, ge=0)
    min_commission: float | None = Field(default=None, ge=0)
    stamp_tax_rate: float | None = Field(default=None, ge=0)
    transfer_fee_rate: float | None = Field(default=None, ge=0)


class AccountUpdateRequest(BaseModel):
    principal: float | None = Field(default=None, ge=0)
    cash_adjustment: float | None = None
    fee_settings: FeeSettingsRequest | None = None


class TradeRequest(BaseModel):
    symbol: str
    name: str = ""
    side: Literal["buy", "sell"]
    trade_time: str = ""
    price: float = Field(gt=0)
    quantity: int = Field(gt=0)
    fee: float | None = Field(default=None, ge=0)
    note: str = ""


def _data_dir(request: Request):
    return request.app.state.repo.store.data_dir


def _name_map(request: Request, symbols: list[str]) -> dict[str, str | None]:
    if not symbols:
        return {}
    try:
        df = request.app.state.repo.get_instruments()
        if df.is_empty() or "symbol" not in df.columns or "name" not in df.columns:
            return {}
        rows = df.filter(pl.col("symbol").is_in(symbols)).select(["symbol", "name"]).to_dicts()
        return {row["symbol"]: row.get("name") for row in rows}
    except Exception as e:  # noqa: BLE001
        logger.debug("trading name lookup failed: %s", e)
        return {}


def _price_map(request: Request, symbols: list[str]) -> dict[str, float | None]:
    if not symbols:
        return {}
    out: dict[str, float | None] = {}

    qs = getattr(request.app.state, "quote_service", None)
    if qs:
        try:
            df = qs.get_quotes_compat()
            if not df.is_empty() and "symbol" in df.columns:
                df = df.filter(pl.col("symbol").is_in(symbols))
                price_col = "last_price" if "last_price" in df.columns else "close"
                if price_col in df.columns:
                    for row in df.select(["symbol", price_col]).to_dicts():
                        value = row.get(price_col)
                        if value is not None:
                            out[row["symbol"]] = float(value)
        except Exception as e:  # noqa: BLE001
            logger.debug("trading realtime price lookup failed: %s", e)

    missing = [symbol for symbol in symbols if symbol not in out]
    if not missing:
        return out

    repo = request.app.state.repo
    end = date.today()
    start = end - timedelta(days=14)
    for symbol in missing:
        try:
            df = repo.get_daily(symbol, start, end)
            if not df.is_empty() and "close" in df.columns:
                row = df.sort("date").tail(1).to_dicts()[0]
                value = row.get("close")
                if value is not None:
                    out[symbol] = float(value)
        except Exception as e:  # noqa: BLE001
            logger.debug("trading daily price lookup failed for %s: %s", symbol, e)
    return out


def _portfolio_response(request: Request) -> dict:
    data_dir = _data_dir(request)
    trades = trading_journal.list_trades(data_dir)
    symbols = sorted({str(t.get("symbol") or "").strip().upper() for t in trades if t.get("symbol")})
    return trading_journal.build_portfolio(
        data_dir,
        price_map=_price_map(request, symbols),
        name_map=_name_map(request, symbols),
    )


@router.get("/portfolio")
def get_portfolio(request: Request):
    return _portfolio_response(request)


@router.get("/account")
def get_account(request: Request):
    return {"account": trading_journal.load_journal(_data_dir(request))["account"]}


@router.put("/account")
def update_account(request: Request, req: AccountUpdateRequest):
    updates = req.model_dump(exclude_none=True)
    if req.fee_settings is not None:
        updates["fee_settings"] = req.fee_settings.model_dump(exclude_none=True)
    return {"account": trading_journal.update_account(_data_dir(request), updates)}


@router.get("/trades")
def list_trades(request: Request):
    return {"trades": trading_journal.list_trades(_data_dir(request))}


@router.post("/trades")
def add_trade(request: Request, req: TradeRequest):
    try:
        trade = trading_journal.add_trade(_data_dir(request), req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"trade": trade, "portfolio": _portfolio_response(request)}


@router.put("/trades/{trade_id}")
def update_trade(request: Request, trade_id: str, req: TradeRequest):
    try:
        trade = trading_journal.update_trade(_data_dir(request), trade_id, req.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if trade is None:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return {"trade": trade, "portfolio": _portfolio_response(request)}


@router.delete("/trades/{trade_id}")
def delete_trade(request: Request, trade_id: str):
    try:
        ok = trading_journal.delete_trade(_data_dir(request), trade_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not ok:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return {"ok": True, "portfolio": _portfolio_response(request)}
