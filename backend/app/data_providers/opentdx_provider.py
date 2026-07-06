"""OpenTDX provider implementation."""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from math import ceil

import polars as pl
from opentdx.const import ADJUST, CATEGORY, MARKET, PERIOD
from opentdx.tdxClient import TdxClient
from opentdx.utils.help import query_market

from app.data_providers.base import AssetType, ProviderCapabilities
from app.data_providers.normalizer import normalize_daily, normalize_instruments

logger = logging.getLogger(__name__)

_MARKETS = (MARKET.SH, MARKET.SZ, MARKET.BJ)
_MINUTE_KLINE_PAGE_SIZE = 800
_MINUTE_KLINE_MAX_PAGES = 24
_MINUTE_PERIODS = {PERIOD.MIN_1, PERIOD.MIN_5, PERIOD.MIN_15, PERIOD.MIN_30, PERIOD.MIN_60}


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


def _minute_count_for_range(start_time: datetime | None, end_time: datetime | None, fallback: int) -> int:
    if start_time and end_time:
        # The TDX minute API returns the latest N bars, then local code filters the target range.
        # Historical date requests need enough bars to cover the span from that date to today.
        span_days = max((date.today() - start_time.date()).days + 1, 1)
        range_days = max((end_time.date() - start_time.date()).days + 1, 1)
        return max(max(span_days, range_days) * 270 + 60, fallback)
    return max(fallback, 1)


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


def _coerce_datetime(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    try:
        text = str(value).strip()
        if not text:
            return None
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:  # noqa: BLE001
        return None


def _coerce_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_tick_datetime(trade_date: date, value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, time):
        return datetime.combine(trade_date, value)
    if isinstance(value, (int, float)):
        minutes = int(value)
        if 0 <= minutes < 24 * 60:
            return datetime.combine(trade_date, time(minutes // 60, minutes % 60))
        return None

    text = str(value).strip()
    if not text:
        return None
    try:
        if "T" in text or "-" in text:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        parts = text.split(":")
        if len(parts) >= 2:
            return datetime.combine(trade_date, time(int(parts[0]), int(parts[1])))
    except Exception:  # noqa: BLE001
        return None
    return None


def _minute_page_limit(start_time: datetime | None, end_time: datetime | None) -> int:
    if not start_time or not end_time:
        return 1
    expected_count = _minute_count_for_range(start_time, end_time, _MINUTE_KLINE_PAGE_SIZE)
    return max(2, min(ceil(expected_count / _MINUTE_KLINE_PAGE_SIZE) + 1, _MINUTE_KLINE_MAX_PAGES))


def _fetch_minute_kline_pages(
    client: TdxClient,
    market: MARKET,
    code: str,
    period: PERIOD,
    start_time: datetime | None,
    end_time: datetime | None,
) -> list[dict]:
    if period not in _MINUTE_PERIODS:
        return client.stock_kline(market, code, period, count=_MINUTE_KLINE_PAGE_SIZE, adjust=ADJUST.NONE)

    rows: list[dict] = []
    offset = 0
    for _ in range(_minute_page_limit(start_time, end_time)):
        page = client.stock_kline(
            market,
            code,
            period,
            start=offset,
            count=_MINUTE_KLINE_PAGE_SIZE,
            adjust=ADJUST.NONE,
        )
        if not page:
            break
        rows.extend(page)

        page_datetimes = [
            dt for dt in (_coerce_datetime(row.get("datetime") or row.get("date")) for row in page)
            if dt is not None
        ]
        if start_time and page_datetimes and min(page_datetimes) <= start_time:
            break
        if len(page) < _MINUTE_KLINE_PAGE_SIZE or not page_datetimes:
            break
        offset += len(page)
    return rows


def _minute_rows_to_frame(rows: list[dict], normalized_symbol: str, freq: str) -> pl.DataFrame:
    records = []
    for row in rows or []:
        dt = row.get("datetime") or row.get("date")
        records.append({
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
    return _finalize_minute_frame(records)


def _finalize_minute_frame(records: list[dict]) -> pl.DataFrame:
    df = pl.DataFrame(records) if records else pl.DataFrame()
    if df.is_empty():
        return df
    df = df.with_columns([
        pl.col("datetime").cast(pl.Datetime("us"), strict=False),
        pl.col("open").cast(pl.Float64, strict=False),
        pl.col("high").cast(pl.Float64, strict=False),
        pl.col("low").cast(pl.Float64, strict=False),
        pl.col("close").cast(pl.Float64, strict=False),
        pl.col("volume").cast(pl.Float64, strict=False),
        pl.col("amount").cast(pl.Float64, strict=False),
    ])
    return (
        df.filter(pl.col("datetime").is_not_null())
        .unique(subset=["symbol", "datetime"], keep="last")
        .sort(["symbol", "datetime"])
    )


def _filter_minute_frame(
    df: pl.DataFrame,
    start_time: datetime | None,
    end_time: datetime | None,
) -> pl.DataFrame:
    if df.is_empty():
        return df
    if start_time:
        df = df.filter(pl.col("datetime") >= start_time)
    if end_time:
        df = df.filter(pl.col("datetime") <= end_time)
    return df.sort(["symbol", "datetime"]) if not df.is_empty() else df


def _single_day_for_tick_fallback(
    period: PERIOD,
    start_time: datetime | None,
    end_time: datetime | None,
) -> date | None:
    if period != PERIOD.MIN_1 or not start_time or not end_time:
        return None
    trade_date = start_time.date()
    return trade_date if end_time.date() == trade_date else None


def _tick_chart_to_minute_frame(
    ticks: list[dict],
    normalized_symbol: str,
    trade_date: date,
    freq: str,
) -> pl.DataFrame:
    grouped: dict[datetime, dict] = {}
    prev_cum_volume: float | None = None
    prev_cum_amount: float | None = None

    for row in ticks or []:
        tick_dt = _coerce_tick_datetime(
            trade_date,
            row.get("time") or row.get("datetime") or row.get("minutes"),
        )
        price = _coerce_float(row.get("price") if row.get("price") is not None else row.get("close"))
        if tick_dt is None or price is None or price <= 0:
            continue

        minute_dt = tick_dt.replace(second=0, microsecond=0)
        cum_volume = _coerce_float(row.get("vol") if row.get("vol") is not None else row.get("volume"))
        if cum_volume is None:
            volume_delta = 0.0
        elif prev_cum_volume is None:
            volume_delta = max(cum_volume, 0.0)
            prev_cum_volume = cum_volume
        else:
            volume_delta = cum_volume - prev_cum_volume if cum_volume >= prev_cum_volume else cum_volume
            volume_delta = max(volume_delta, 0.0)
            prev_cum_volume = cum_volume

        avg_price = _coerce_float(row.get("avg") if row.get("avg") is not None else row.get("average"))
        if avg_price is not None and avg_price > 0 and cum_volume is not None:
            cum_amount = avg_price * cum_volume * 100
            amount_delta = max(cum_amount, 0.0) if prev_cum_amount is None else max(cum_amount - prev_cum_amount, 0.0)
            prev_cum_amount = cum_amount
        else:
            amount_delta = price * volume_delta * 100

        bucket = grouped.setdefault(minute_dt, {"prices": [], "volume": 0.0, "amount": 0.0})
        bucket["prices"].append(price)
        bucket["volume"] += volume_delta
        bucket["amount"] += amount_delta

    records = []
    for minute_dt in sorted(grouped):
        bucket = grouped[minute_dt]
        prices = bucket["prices"]
        records.append({
            "symbol": normalized_symbol,
            "datetime": minute_dt,
            "open": prices[0],
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": bucket["volume"],
            "amount": bucket["amount"],
            "freq": freq,
        })
    return _finalize_minute_frame(records)


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
        for symbol in symbols:
            market, code, normalized_symbol = _split_symbol(symbol)
            try:
                raw = _fetch_minute_kline_pages(
                    self._client,
                    market,
                    code,
                    period,
                    start_time,
                    end_time,
                )
            except Exception as e:  # noqa: BLE001
                logger.warning("OpenTDX minute %s failed: %s", symbol, e)
                raw = []

            df = _filter_minute_frame(
                _minute_rows_to_frame(raw, normalized_symbol, freq),
                start_time,
                end_time,
            )
            if df.is_empty():
                tick_date = _single_day_for_tick_fallback(period, start_time, end_time)
                if tick_date is not None:
                    try:
                        ticks = self._client.stock_tick_chart(market, code, date=tick_date)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("OpenTDX tick chart %s %s failed: %s", symbol, tick_date, e)
                        ticks = []
                    df = _filter_minute_frame(
                        _tick_chart_to_minute_frame(ticks, normalized_symbol, tick_date, freq),
                        start_time,
                        end_time,
                    )
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
