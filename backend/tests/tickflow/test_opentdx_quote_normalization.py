from __future__ import annotations

from opentdx.const import MARKET

from app.tickflow.client import _normalize_quote


def test_opentdx_zero_realtime_price_falls_back_to_previous_close():
    quote = _normalize_quote({
        "market": MARKET.SZ,
        "code": "000001",
        "close": 0.0,
        "pre_close": 10.05,
        "vol": 0,
        "amount": 0.0,
    })

    assert quote["symbol"] == "000001.SZ"
    assert quote["last_price"] == 10.05
    assert quote["prev_close"] == 10.05
    assert quote["change_amount"] == 0
    assert quote["change_pct"] == 0
