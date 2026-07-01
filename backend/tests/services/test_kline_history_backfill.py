from __future__ import annotations

from datetime import date, timedelta

import polars as pl

from app.services import kline_history


def _bars(symbol: str, start: date, n: int) -> pl.DataFrame:
    rows = []
    for i in range(n):
        d = start + timedelta(days=i)
        close = 10 + i * 0.01
        rows.append({
            "symbol": symbol,
            "date": d,
            "open": close - 0.02,
            "high": close + 0.05,
            "low": close - 0.05,
            "close": close,
            "volume": 1_000_000 + i,
            "amount": 10_000_000 + i,
        })
    return pl.DataFrame(rows)


class _Repo:
    def __init__(self, local: pl.DataFrame) -> None:
        self.local = local

    def get_daily(self, symbol: str, start: date, end: date) -> pl.DataFrame:  # noqa: ARG002
        return self.local

    def get_instruments(self) -> pl.DataFrame:
        return pl.DataFrame()


def test_load_daily_history_backfills_when_local_has_only_live_candle(monkeypatch):
    symbol = "000001.SZ"
    start = date(2026, 1, 1)
    end = date(2026, 7, 1)
    local = _bars(symbol, end, 1)
    raw = _bars(symbol, date(2025, 12, 1), 230)
    calls = []

    def fake_sync_daily_batch(symbols, **kwargs):
        calls.append((symbols, kwargs))
        return raw

    monkeypatch.setattr(kline_history.kline_sync, "sync_daily_batch", fake_sync_daily_batch)

    df, source = kline_history.load_daily_history(_Repo(local), symbol, start, end)

    assert source == "opentdx"
    assert calls
    assert df.height > 100
    assert df["date"].min() >= start
    assert df["date"].max() <= end
    assert "ma5" in df.columns


def test_load_daily_history_keeps_local_when_coverage_is_enough(monkeypatch):
    symbol = "000001.SZ"
    start = date(2026, 1, 1)
    end = date(2026, 7, 1)
    local = _bars(symbol, start, (end - start).days + 1)

    def fail_sync_daily_batch(*args, **kwargs):  # noqa: ARG001
        raise AssertionError("OpenTDX should not be called for sufficient local history")

    monkeypatch.setattr(kline_history.kline_sync, "sync_daily_batch", fail_sync_daily_batch)

    df, source = kline_history.load_daily_history(_Repo(local), symbol, start, end)

    assert source == "enriched"
    assert df.height == local.height


def test_load_daily_history_falls_back_to_local_if_opentdx_empty(monkeypatch):
    symbol = "000001.SZ"
    start = date(2026, 1, 1)
    end = date(2026, 7, 1)
    local = _bars(symbol, end, 1)

    monkeypatch.setattr(
        kline_history.kline_sync,
        "sync_daily_batch",
        lambda *args, **kwargs: pl.DataFrame(),
    )

    df, source = kline_history.load_daily_history(_Repo(local), symbol, start, end)

    assert source == "enriched"
    assert df.height == 1
