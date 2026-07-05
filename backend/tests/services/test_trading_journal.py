from __future__ import annotations

import pytest

from app.services import trading_journal


def test_fee_calculation_uses_side_specific_taxes():
    settings = {
        "commission_rate": 0.00025,
        "min_commission": 5,
        "stamp_tax_rate": 0.0005,
        "transfer_fee_rate": 0.00001,
    }

    buy_fee = trading_journal.calculate_fee("buy", 10, 1000, settings)
    sell_fee = trading_journal.calculate_fee("sell", 10, 1000, settings)

    assert buy_fee == 5.1
    assert sell_fee == 10.1


def test_buy_sell_derives_cash_position_and_pnl(tmp_path):
    trading_journal.update_account(tmp_path, {
        "principal": 100000,
        "fee_settings": {
            "commission_rate": 0,
            "min_commission": 0,
            "stamp_tax_rate": 0,
            "transfer_fee_rate": 0,
        },
    })
    trading_journal.add_trade(tmp_path, {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "side": "buy",
        "trade_time": "2026-06-01T10:00:00",
        "price": 10,
        "quantity": 1000,
    })
    trading_journal.add_trade(tmp_path, {
        "symbol": "000001.SZ",
        "name": "平安银行",
        "side": "sell",
        "trade_time": "2026-06-05T10:00:00",
        "price": 12,
        "quantity": 400,
    })

    portfolio = trading_journal.build_portfolio(tmp_path, price_map={"000001.SZ": 11})

    assert portfolio["summary"]["cash"] == 94800
    assert portfolio["summary"]["market_value"] == 6600
    assert portfolio["summary"]["total_assets"] == 101400
    assert portfolio["summary"]["realized_pnl"] == 800
    assert portfolio["summary"]["unrealized_pnl"] == 600
    assert portfolio["positions"][0]["quantity"] == 600
    assert portfolio["positions"][0]["avg_cost"] == 10


def test_sell_more_than_holding_is_rejected(tmp_path):
    trading_journal.add_trade(tmp_path, {
        "symbol": "000001.SZ",
        "side": "buy",
        "trade_time": "2026-06-01T10:00:00",
        "price": 10,
        "quantity": 100,
        "fee": 0,
    })

    with pytest.raises(ValueError, match="卖出数量超过当前持仓"):
        trading_journal.add_trade(tmp_path, {
            "symbol": "000001.SZ",
            "side": "sell",
            "trade_time": "2026-06-02T10:00:00",
            "price": 10,
            "quantity": 200,
            "fee": 0,
        })


def test_portfolio_context_for_symbol_marks_current_holding(tmp_path):
    trading_journal.add_trade(tmp_path, {
        "symbol": "000001.SZ",
        "side": "buy",
        "trade_time": "2026-06-01T10:00:00",
        "price": 10,
        "quantity": 100,
        "fee": 0,
    })
    trading_journal.add_trade(tmp_path, {
        "symbol": "600000.SH",
        "side": "buy",
        "trade_time": "2026-06-02T10:00:00",
        "price": 8,
        "quantity": 200,
        "fee": 0,
    })

    context = trading_journal.portfolio_context_for_symbol(tmp_path, "000001.SZ", latest_price=12)

    assert context["held"] is True
    assert context["position"]["quantity"] == 100
    assert context["position"]["unrealized_pnl"] == 200
    assert context["has_positions"] is True
    assert context["position_count"] == 2
    assert {p["symbol"] for p in context["positions"]} == {"000001.SZ", "600000.SH"}
    assert context["account"]["market_value"] == 2800
