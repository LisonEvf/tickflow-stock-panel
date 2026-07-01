from __future__ import annotations

from types import SimpleNamespace

import polars as pl

from app.api import financials


def _request(data_dir):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repo=SimpleNamespace(store=SimpleNamespace(data_dir=data_dir)),
                financial_scheduler=None,
            ),
        ),
    )


def test_financial_status_is_not_capability_locked(tmp_path):
    result = financials.financial_status(_request(tmp_path))

    assert result["available"] is False
    assert set(result["tables"]) == {"metrics", "income", "balance_sheet", "cash_flow"}
    assert result["last_sync"] == {}
    assert all(info == {"rows": 0, "symbols": 0} for info in result["tables"].values())


def test_financial_metrics_reads_local_data_without_capability(tmp_path):
    out_dir = tmp_path / "financials" / "metrics"
    out_dir.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "period_end": "2026-04-25",
                "eps_basic": 0.67,
            },
            {
                "symbol": "600000.SH",
                "period_end": "2026-04-25",
                "eps_basic": 0.2,
            },
        ],
    ).write_parquet(out_dir / "part.parquet")

    status = financials.financial_status(_request(tmp_path))
    result = financials.get_metrics(_request(tmp_path), symbol="000001.SZ")

    assert status["available"] is True
    assert status["tables"]["metrics"] == {"rows": 2, "symbols": 2}
    assert "metrics" in status["last_sync"]
    assert result["data"] == [
        {
            "symbol": "000001.SZ",
            "period_end": "2026-04-25",
            "eps_basic": 0.67,
        },
    ]
