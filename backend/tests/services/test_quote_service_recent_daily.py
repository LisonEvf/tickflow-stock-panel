from __future__ import annotations

from datetime import date

import polars as pl

from app.services.quote_service import QuoteService


def test_recent_daily_reader_normalizes_mixed_date_schemas(tmp_path):
    daily_dir = tmp_path / "kline_daily"

    old_dir = daily_dir / "date=2026-06-30"
    old_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": ["2026-06-30"],
            "open": [10.0],
            "high": [10.2],
            "low": [9.9],
            "close": [10.1],
            "volume": [1000.0],
            "amount": [10_000.0],
        }
    ).write_parquet(old_dir / "part.parquet")

    live_dir = daily_dir / "date=2026-07-01"
    live_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "symbol": ["000002.SZ"],
            "date": [date(2026, 7, 1)],
            "open": [3.0],
            "high": [3.1],
            "low": [2.9],
            "close": [3.05],
            "volume": [2000.0],
            "amount": [20_000.0],
        }
    ).write_parquet(live_dir / "part.parquet")

    df = QuoteService._read_recent_daily_partitions(daily_dir, date(2026, 6, 1))

    assert df.schema["date"] == pl.Date
    assert df.select("symbol").to_series().to_list() == ["000001.SZ", "000002.SZ"]
    assert df.select("date").to_series().to_list() == [date(2026, 6, 30), date(2026, 7, 1)]


def test_quotes_compat_keeps_names_from_raw_quote_cache():
    service = QuoteService()
    service._quotes_cache = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "name": ["平安银行"],
            "close": [10.07],
            "prev_close": [10.05],
            "change_pct": [0.00199],
            "amount": [370_000_000.0],
            "volume": [36_000_000.0],
        }
    )

    df = service.get_quotes_compat()

    assert "name" in df.columns
    assert df.item(0, "name") == "平安银行"


def test_merge_quote_extra_overlays_sparse_enriched_values():
    enriched = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "date": [date(2026, 7, 1)],
            "close": [10.07],
            "change_pct": [None],
            "turnover_rate": [None],
        }
    )
    quote_extra = pl.DataFrame(
        {
            "symbol": ["000001.SZ"],
            "prev_close": [10.05],
            "change_pct": [0.001990049751243724],
            "change_amount": [0.02],
            "turnover_rate": [1.23],
        }
    )

    merged = QuoteService._merge_quote_extra(enriched, quote_extra)

    assert merged.item(0, "prev_close") == 10.05
    assert merged.item(0, "change_pct") == 0.001990049751243724
    assert merged.item(0, "change_amount") == 0.02
    assert merged.item(0, "turnover_rate") == 1.23
