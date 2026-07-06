from datetime import date, datetime, time, timedelta

import polars as pl
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import kline

SYMBOL = "000001.SZ"


def _minute_df(trade_date: date, count: int = 240, start: time = time(9, 30)) -> pl.DataFrame:
    base = datetime.combine(trade_date, start)
    return pl.DataFrame([
        {
            "symbol": SYMBOL,
            "datetime": base + timedelta(minutes=i),
            "open": 10.0,
            "high": 10.1,
            "low": 9.9,
            "close": 10.0 + i * 0.001,
            "volume": 1000 + i,
            "amount": 10000 + i,
            "freq": "1m",
        }
        for i in range(count)
    ])


class FakeRepo:
    def __init__(
        self,
        minute_by_date: dict[date, pl.DataFrame] | None = None,
        previous_date: date | None = None,
        previous_dates: list[date] | None = None,
    ):
        self.minute_by_date = minute_by_date or {}
        self.previous_dates = sorted(previous_dates or ([previous_date] if previous_date else []))

    def get_minute(self, symbol: str, trade_date: date) -> pl.DataFrame:
        assert symbol == SYMBOL
        return self.minute_by_date.get(trade_date, pl.DataFrame())

    def execute_one(self, query: str, params: list | None = None):
        if "FROM instruments" in query:
            return ("Ping An Bank", None, None)
        if "max(CAST(datetime AS DATE))" in query:
            return None
        if "max(date)" in query and self.previous_dates:
            before = params[-1] if params else date.max
            candidates = [d for d in self.previous_dates if d < before]
            return (max(candidates),) if candidates else None
        return None


def _client(repo: FakeRepo) -> TestClient:
    app = FastAPI()
    app.state.repo = repo
    app.include_router(kline.router)
    return TestClient(app)


def test_minute_without_date_falls_back_to_previous_trading_day(monkeypatch):
    today = date.today()
    previous = today - timedelta(days=1)
    repo = FakeRepo({previous: _minute_df(previous)}, previous_date=previous)

    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", lambda symbol, trade_date: pl.DataFrame())

    resp = _client(repo).get(f"/api/kline/minute?symbol={SYMBOL}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_date"] == str(today)
    assert body["date"] == str(previous)
    assert body["fallback"] is True
    assert body["fallback_reason"] == "requested_date_empty"
    assert body["source"] == "local"
    assert len(body["rows"]) == 240


def test_minute_explicit_today_can_fall_back_to_previous_trading_day(monkeypatch):
    today = date.today()
    previous = today - timedelta(days=1)
    repo = FakeRepo({previous: _minute_df(previous)}, previous_date=previous)

    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", lambda symbol, trade_date: pl.DataFrame())

    resp = _client(repo).get(f"/api/kline/minute?symbol={SYMBOL}&date={today}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_date"] == str(today)
    assert body["date"] == str(previous)
    assert body["fallback"] is True
    assert body["source"] == "local"


def test_minute_fallback_skips_empty_previous_dates(monkeypatch):
    today = date.today()
    empty_previous = today - timedelta(days=1)
    older = today - timedelta(days=3)
    repo = FakeRepo({older: _minute_df(older)}, previous_dates=[older, empty_previous])

    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", lambda symbol, trade_date: pl.DataFrame())

    resp = _client(repo).get(f"/api/kline/minute?symbol={SYMBOL}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_date"] == str(today)
    assert body["date"] == str(older)
    assert body["fallback"] is True
    assert body["source"] == "local"
    assert len(body["rows"]) == 240


def test_minute_explicit_historical_date_uses_that_date_without_fallback(monkeypatch):
    historical = date(2026, 6, 30)
    previous = historical - timedelta(days=1)
    repo = FakeRepo(previous_date=previous)
    live_df = _minute_df(historical, count=2, start=time(9, 25))

    def fake_fetch(symbol: str, trade_date: date) -> pl.DataFrame:
        assert symbol == SYMBOL
        return live_df if trade_date == historical else pl.DataFrame()

    monkeypatch.setattr(kline.kline_sync, "fetch_minute_single", fake_fetch)

    resp = _client(repo).get(f"/api/kline/minute?symbol={SYMBOL}&date={historical}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["requested_date"] == str(historical)
    assert body["date"] == str(historical)
    assert body["fallback"] is False
    assert body["source"] == "live"
    assert len(body["rows"]) == 2
    assert body["rows"][0]["datetime"].startswith(f"{historical}T09:25")
