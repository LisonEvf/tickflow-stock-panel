from __future__ import annotations

from app.services.stock_analyzer import (
    _PROMPT_PROFILE_OFFICIAL,
    _build_user_prompt,
    _portfolio_meta,
    _system_prompt_for_profile,
)


def test_stock_prompt_includes_manual_portfolio_context():
    prompt = _build_user_prompt(
        kline_tail=[{"date": "2026-07-01", "close": 12.0}],
        fins={},
        levels={"sr": []},
        close=12.0,
        portfolio_context={
            "symbol": "000001.SZ",
            "held": True,
            "position": {"symbol": "000001.SZ", "quantity": 1000, "avg_cost": 10.5, "unrealized_pnl": 1500},
            "has_positions": True,
            "position_count": 2,
            "positions": [
                {"symbol": "000001.SZ", "quantity": 1000, "weight": 0.2},
                {"symbol": "600000.SH", "quantity": 500, "weight": 0.08},
            ],
            "account": {"cash": 50000, "market_value": 12000, "total_assets": 62000, "position_ratio": 0.2},
        },
        symbol="000001.SZ",
        focus="",
    )

    assert "真实账户/仓位上下文" in prompt
    assert '"held": true' in prompt
    assert '"has_positions": true' in prompt
    assert '"quantity": 1000' in prompt
    assert '"600000.SH"' in prompt
    assert "不要只给泛泛的买卖区间" in prompt
    assert "持有、加仓、减仓、止损/止盈动作" in prompt


def test_portfolio_meta_exposes_compact_position_state():
    meta = _portfolio_meta({
        "held": True,
        "has_positions": True,
        "position_count": 2,
        "position": {
            "symbol": "000001.SZ",
            "name": "平安银行",
            "quantity": 1000,
            "avg_cost": 10.5,
            "latest_price": 12.0,
            "market_value": 12000,
            "unrealized_pnl": 1500,
            "unrealized_pnl_pct": 0.142857,
            "weight": 0.2,
            "cost_basis": 10500,
        },
        "account": {
            "cash": 50000,
            "market_value": 12000,
            "total_assets": 62000,
            "position_ratio": 0.2,
            "realized_pnl": 300,
        },
    })

    assert meta["held"] is True
    assert meta["position_count"] == 2
    assert meta["position"]["quantity"] == 1000
    assert meta["position"]["weight"] == 0.2
    assert "cost_basis" not in meta["position"]
    assert meta["account"]["position_ratio"] == 0.2


def test_official_prompt_profile_keeps_data_context_without_generic_framework():
    system_prompt = _system_prompt_for_profile(_PROMPT_PROFILE_OFFICIAL)
    prompt = _build_user_prompt(
        kline_tail=[{"date": "2026-07-01", "close": 12.0}],
        fins={},
        levels={"sr": []},
        close=12.0,
        portfolio_context={
            "symbol": "000001.SZ",
            "held": False,
            "has_positions": False,
            "position_count": 0,
            "positions": [],
            "account": {"cash": 100000, "market_value": 0, "total_assets": 100000, "position_ratio": 0},
        },
        symbol="000001.SZ",
        focus="",
        prompt_profile=_PROMPT_PROFILE_OFFICIAL,
    )

    assert "你已内置的金融分析能力" in system_prompt
    assert "15 年 A 股一线实战经验" not in system_prompt
    assert "以下是用户手工同步的真实账户/仓位上下文" in prompt
    assert '"has_positions": false' in prompt
    assert "请按系统提示词第 4 节" not in prompt
    assert "不要编造财务指标" in prompt
