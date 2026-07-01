from __future__ import annotations

import polars as pl

from app.services import financial_sync
from app.tickflow.capabilities import CapabilitySet


def test_financial_sync_writes_rows_without_capability(monkeypatch, tmp_path):
    instruments_dir = tmp_path / "instruments"
    instruments_dir.mkdir(parents=True)
    pl.DataFrame({"symbol": ["000001.SZ"]}).write_parquet(instruments_dir / "instruments.parquet")

    class FakeFinancials:
        def metrics(self, symbols, latest=True):  # noqa: ARG002
            return {
                "000001.SZ": [
                    {
                        "period_end": "2026-04-25",
                        "announce_date": "2026-04-25",
                        "eps_basic": 0.67,
                    },
                ],
            }

        income = metrics
        balance_sheet = metrics
        cash_flow = metrics

    class FakeClient:
        financials = FakeFinancials()

    monkeypatch.setattr("app.tickflow.client.get_client", lambda: FakeClient())

    rows = financial_sync.sync_metrics(tmp_path, CapabilitySet())

    assert rows == 1
    written = pl.read_parquet(tmp_path / "financials" / "metrics" / "part.parquet")
    assert written.to_dicts() == [
        {
            "period_end": "2026-04-25",
            "announce_date": "2026-04-25",
            "eps_basic": 0.67,
            "symbol": "000001.SZ",
        },
    ]
