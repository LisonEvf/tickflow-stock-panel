from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from app.services.market_overview_builder import build_market_overview


class _Repo:
    def __init__(self, data_dir) -> None:
        self.store = SimpleNamespace(data_dir=data_dir)

    def execute_all(self, *_args, **_kwargs):
        return []


class _QuoteService:
    def __init__(self) -> None:
        self.refresh_calls = 0
        self._quotes = pl.DataFrame()

    def status(self) -> dict:
        return {
            "enabled": False,
            "running": False,
            "quote_age_ms": None,
            "is_trading_hours": False,
        }

    def get_enriched_today(self):
        return pl.DataFrame(), None

    def get_quotes_compat(self) -> pl.DataFrame:
        return self._quotes

    def get_index_quotes(self, symbols: list[str] | None = None) -> pl.DataFrame:
        df = pl.DataFrame(
            [
                {
                    "symbol": "000001.SH",
                    "name": "上证指数",
                    "last_price": 4094.4,
                    "change_pct": 0.50,
                    "change_amount": 20.5,
                }
            ]
        )
        return df.filter(pl.col("symbol").is_in(symbols)) if symbols else df

    def refresh(self) -> dict:
        self.refresh_calls += 1
        self._quotes = pl.DataFrame(
            [
                {
                    "symbol": "000001.SZ",
                    "name": "平安银行",
                    "close": 10.05,
                    "last_price": 10.05,
                    "change_pct": 0.03,
                    "amount": 1_000_000.0,
                    "volume": 100_000.0,
                    "turnover_rate": 1.5,
                },
                {
                    "symbol": "000002.SZ",
                    "name": "万科A",
                    "close": 6.2,
                    "last_price": 6.2,
                    "change_pct": -0.02,
                    "amount": 500_000.0,
                    "volume": 80_000.0,
                    "turnover_rate": 0.8,
                },
            ]
        )
        return self.status()


def test_market_overview_refreshes_and_uses_opentdx_quote_cache(tmp_path):
    quote_service = _QuoteService()

    overview = build_market_overview(
        _Repo(tmp_path),
        quote_service=quote_service,
        depth_service=None,
        as_of=None,
    )

    assert quote_service.refresh_calls == 1
    assert overview["as_of"] is not None
    assert overview["breadth"]["total"] == 2
    assert overview["breadth"]["up"] == 1
    assert overview["breadth"]["down"] == 1
    assert overview["amount"]["total"] == 1_500_000.0
    assert overview["top_gainers"][0]["symbol"] == "000001.SZ"
    assert overview["top_losers"][0]["symbol"] == "000002.SZ"


def test_market_overview_keeps_premarket_flat_opentdx_quotes(tmp_path):
    quote_service = _QuoteService()
    quote_service._quotes = pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "close": 10.05,
                "last_price": 10.05,
                "change_pct": 0.0,
                "amount": 0.0,
                "volume": 0.0,
            },
            {
                "symbol": "000002.SZ",
                "name": "万科A",
                "close": 2.96,
                "last_price": 2.96,
                "change_pct": 0.0,
                "amount": 0.0,
                "volume": 0.0,
            },
        ]
    )

    overview = build_market_overview(
        _Repo(tmp_path),
        quote_service=quote_service,
        depth_service=None,
        as_of=None,
    )

    assert quote_service.refresh_calls == 0
    assert overview["breadth"]["total"] == 2
    assert overview["breadth"]["flat"] == 2
    assert overview["top_gainers"][0]["close"] == 10.05


def test_market_overview_infers_limit_counts_from_realtime_prices(tmp_path):
    quote_service = _QuoteService()
    quote_service._quotes = pl.DataFrame(
        [
            {
                "symbol": "300001.SZ",
                "name": "特锐德",
                "prev_close": 10.0,
                "close": 12.0,
                "high": 12.0,
                "change_pct": 0.20,
                "amount": 1_000_000.0,
                "volume": 100_000.0,
            },
            {
                "symbol": "000001.SZ",
                "name": "平安银行",
                "prev_close": 10.0,
                "close": 9.0,
                "high": 10.0,
                "change_pct": -0.10,
                "amount": 500_000.0,
                "volume": 80_000.0,
            },
            {
                "symbol": "000002.SZ",
                "name": "万科A",
                "prev_close": 10.0,
                "close": 10.5,
                "high": 11.0,
                "change_pct": 0.05,
                "amount": 400_000.0,
                "volume": 70_000.0,
            },
        ]
    )

    overview = build_market_overview(
        _Repo(tmp_path),
        quote_service=quote_service,
        depth_service=None,
        as_of=None,
    )

    assert overview["limit"]["limit_up"] == 1
    assert overview["limit"]["limit_down"] == 1
    assert overview["limit"]["broken"] == 1
    assert overview["limit"]["max_boards"] == 1
    assert overview["limit"]["tiers"] == [{"boards": 1, "count": 1}]


def test_market_overview_uses_openkpl_rank_when_ext_data_missing(tmp_path, monkeypatch):
    calls: list[str] = []

    def fake_openkpl_rank(kind: str, limit: int = 5) -> dict:
        calls.append(kind)
        return {
            "leading": [
                {
                    "name": "芯片" if kind == "concept" else "半导体",
                    "count": 0,
                    "avg_pct": 0.025,
                    "up_count": 0,
                    "down_count": 0,
                    "amount": 100_000_000.0,
                    "leader": None,
                    "source": "openkpl",
                    "plate_id": "801001",
                }
            ],
            "lagging": [],
        }

    monkeypatch.setattr(
        "app.services.market_overview_builder._openkpl_dimension_rank",
        fake_openkpl_rank,
    )

    overview = build_market_overview(
        _Repo(tmp_path),
        quote_service=_QuoteService(),
        depth_service=None,
        as_of=None,
    )

    assert calls == ["concept", "industry"]
    assert overview["concept_rank"]["leading"][0]["name"] == "芯片"
    assert overview["industry_rank"]["leading"][0]["name"] == "半导体"
    assert overview["concept_rank"]["leading"][0]["source"] == "openkpl"
