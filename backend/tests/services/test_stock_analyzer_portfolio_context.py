from __future__ import annotations

from app.services.stock_analyzer import _build_user_prompt


def test_stock_prompt_includes_manual_portfolio_context():
    prompt = _build_user_prompt(
        kline_tail=[{"date": "2026-07-01", "close": 12.0}],
        fins={},
        levels={"sr": []},
        close=12.0,
        portfolio_context={
            "symbol": "000001.SZ",
            "held": True,
            "position": {"quantity": 1000, "avg_cost": 10.5, "unrealized_pnl": 1500},
            "account": {"cash": 50000, "total_assets": 62000, "position_ratio": 0.2},
        },
        symbol="000001.SZ",
        focus="",
    )

    assert "真实账户/仓位上下文" in prompt
    assert '"held": true' in prompt
    assert '"quantity": 1000' in prompt
    assert "不要只给泛泛的买卖区间" in prompt
