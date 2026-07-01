"""OpenTDX provider implementation."""
from __future__ import annotations

import logging
from datetime import datetime

import polars as pl
from opentdx.const import ADJUST, CATEGORY, MARKET, PERIOD
from opentdx.tdxClient import TdxClient
from opentdx.utils.help import query_market

from app.data_providers.base import AssetType, ProviderCapabilities
from app.data_providers.normalizer import normalize_daily, normalize_instruments

logger = logging.getLogger(__name__)

_MARKETS = (MARKET.SH, MARKET.SZ, MARKET.BJ)


def _market_suffix(market: MARKET) -> str:
    if market == MARKET.SZ:
        return "SZ"
    if market == MARKET.BJ:
        return "BJ"
    return "SH"


def _split_symbol(symbol: str) -> tuple[MARKET, str, str]:
    raw = symbol.strip().upper()
    code, _, suffix = raw.partition(".")
    if suffix == "SH":
        market = MARKET.SH
    elif suffix == "SZ":
        market = MARKET.SZ
    elif suffix == "BJ":
        market = MARKET.BJ
    else:
        market = query_market(code) or MARKET.SH
    return market, code, f"{code}.{_market_suffix(market)}"


def _is_asset_code(code: str, market: MARKET, asset_type: AssetType) -> bool:
    if asset_type == "index":
        return (market == MARKET.SZ and code.startswith("399")) or (
            market == MARKET.SH and code.startswith("000")
        )
    if asset_type == "etf":
        return code.startswith(("15", "16", "18", "50", "51", "52", "56", "58"))
    if market == MARKET.SZ:
        return code.startswith(("00", "30"))
    if market == MARKET.SH:
        return code.startswith(("60", "68"))
    if market == MARKET.BJ:
        return code.startswith(("43", "83", "87", "88", "92"))
    return False


def _period(freq: str = "1d") -> PERIOD:
    f = freq.lower()
    if f in {"1m", "min_1"}:
        return PERIOD.MIN_1
    if f in {"5m", "min_5"}:
        return PERIOD.MIN_5
    if f in {"15m", "min_15"}:
        return PERIOD.MIN_15
    if f in {"30m", "min_30"}:
        return PERIOD.MIN_30
    if f in {"60m", "min_60"}:
        return PERIOD.MIN_60
    return PERIOD.DAILY


def _count_for_range(start_time: datetime | None, end_time: datetime | None, fallback: int) -> int:
    if start_time and end_time:
        return min(max((end_time.date() - start_time.date()).days * 2 + 30, fallback), 800)
    return min(max(fallback, 1), 800)


def _normalize_kline_rows(rows: list[dict], symbol: str) -> pl.DataFrame:
    normalized = []
    for row in rows or []:
        dt = row.get("datetime") or row.get("date")
        normalized.append({
            "symbol": symbol,
            "date": dt,
            "open": row.get("open"),
            "high": row.get("high"),
            "low": row.get("low"),
            "close": row.get("close"),
            "volume": row.get("volume", row.get("vol")),
            "amount": row.get("amount"),
        })
    return normalize_daily(normalized, default_symbol=symbol, source="opentdx")


class OpenTDXProvider:
    name = "opentdx"
    capabilities = ProviderCapabilities(
        instruments=True,
        daily=True,
        adj_factor=False,
        minute=True,
        realtime=True,
        financial=False,
    )

    def __init__(self) -> None:
        self._client = TdxClient()
        self._ensure_connected()

    def _ensure_connected(self) -> None:
        try:
            client = self._client.q_client()
            if not client.connected:
                client.connect().login()
        except Exception as e:  # noqa: BLE001
            logger.debug("OpenTDX connect skipped: %s", e)

    def get_instruments(self, asset_type: AssetType) -> pl.DataFrame:
        rows: list[dict] = []
        for market in _MARKETS:
            try:
                items = self._client.stock_list(market, count=0)
            except Exception as e:  # noqa: BLE001
                logger.warning("OpenTDX instruments %s failed: %s", market, e)
                continue
            exchange = _market_suffix(market)
            for item in items or []:
                code = str(item.get("code") or "").strip()
                if not code or not _is_asset_code(code, market, asset_type):
                    continue
                rows.append({
                    "symbol": f"{code}.{exchange}",
                    "name": item.get("name") or code,
                    "code": code,
                    "exchange": exchange,
                })
        return normalize_instruments(rows, asset_type=asset_type, source=self.name)

    def get_daily(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()

        frames: list[pl.DataFrame] = []
        count = _count_for_range(start_time, end_time, 250)
        for symbol in symbols:
            market, code, normalized_symbol = _split_symbol(symbol)
            try:
                raw = self._client.stock_kline(
                    market,
                    code,
                    PERIOD.DAILY,
                    count=count,
                    adjust=ADJUST.NONE,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("OpenTDX daily %s failed: %s", symbol, e)
                continue
            df = _normalize_kline_rows(raw, normalized_symbol)
            if df.is_empty():
                continue
            if start_time:
                df = df.filter(pl.col("date") >= start_time.date())
            if end_time:
                df = df.filter(pl.col("date") <= end_time.date())
            if not df.is_empty():
                frames.append(df)

        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_adj_factors(
        self,
        symbols: list[str],  # noqa: ARG002
        start_time: datetime | None,  # noqa: ARG002
        end_time: datetime | None,  # noqa: ARG002
        asset_type: AssetType,  # noqa: ARG002
    ) -> pl.DataFrame:
        return pl.DataFrame()

    def get_minute(
        self,
        symbols: list[str],
        start_time: datetime | None,
        end_time: datetime | None,
        asset_type: AssetType,  # noqa: ARG002
        freq: str = "1m",
    ) -> pl.DataFrame:
        if not symbols:
            return pl.DataFrame()

        frames: list[pl.DataFrame] = []
        period = _period(freq)
        count = _count_for_range(start_time, end_time, 240)
        for symbol in symbols:
            market, code, normalized_symbol = _split_symbol(symbol)
            try:
                raw = self._client.stock_kline(
                    market,
                    code,
                    period,
                    count=count,
                    adjust=ADJUST.NONE,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("OpenTDX minute %s failed: %s", symbol, e)
                continue
            rows = []
            for row in raw or []:
                dt = row.get("datetime")
                rows.append({
                    "symbol": normalized_symbol,
                    "datetime": dt,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "volume": row.get("volume", row.get("vol")),
                    "amount": row.get("amount"),
                    "freq": freq,
                })
            df = pl.DataFrame(rows) if rows else pl.DataFrame()
            if df.is_empty():
                continue
            df = df.with_columns([
                pl.col("datetime").cast(pl.Datetime("us"), strict=False),
                pl.col("open").cast(pl.Float64, strict=False),
                pl.col("high").cast(pl.Float64, strict=False),
                pl.col("low").cast(pl.Float64, strict=False),
                pl.col("close").cast(pl.Float64, strict=False),
                pl.col("volume").cast(pl.Float64, strict=False),
                pl.col("amount").cast(pl.Float64, strict=False),
            ])
            if start_time:
                df = df.filter(pl.col("datetime") >= start_time)
            if end_time:
                df = df.filter(pl.col("datetime") <= end_time)
            if not df.is_empty():
                frames.append(df)

        return pl.concat(frames, how="diagonal_relaxed") if frames else pl.DataFrame()

    def get_realtime(
        self,
        universes: list[str] | None = None,
        symbols: list[str] | None = None,
    ) -> pl.DataFrame:
        try:
            if symbols:
                pairs = [_split_symbol(symbol)[:2] for symbol in symbols]
                rows = self._client.stock_quotes(pairs)
            elif universes and "CN_Equity_A" in universes:
                rows = self._client.stock_quotes_list(category=CATEGORY.A, count=0)
            else:
                return pl.DataFrame()
        except Exception as e:  # noqa: BLE001
            logger.warning("OpenTDX realtime failed: %s", e)
            return pl.DataFrame()

        records = []
        for row in rows or []:
            code = str(row.get("code") or "")
            try:
                market = MARKET(row.get("market"))
            except Exception:  # noqa: BLE001
                market = query_market(code) or MARKET.SH
            last_price = row.get("close")
            prev_close = row.get("pre_close")
            if last_price in (None, 0, 0.0) and prev_close not in (None, 0, 0.0):
                last_price = prev_close
            change_amount = None
            change_pct = None
            if last_price is not None and prev_close not in (None, 0):
                change_amount = float(last_price) - float(prev_close)
                change_pct = change_amount / float(prev_close)
            records.append({
                "symbol": f"{code}.{_market_suffix(market)}",
                "open": row.get("open"),
                "high": row.get("high"),
                "low": row.get("low"),
                "last_price": last_price,
                "close": last_price,
                "prev_close": prev_close,
                "volume": row.get("volume", row.get("vol")),
                "amount": row.get("amount"),
                "change_amount": change_amount,
                "change_pct": change_pct,
                "turnover_rate": row.get("turnover"),
            })
        return pl.DataFrame(records) if records else pl.DataFrame()
