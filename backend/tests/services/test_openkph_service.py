from __future__ import annotations

from types import SimpleNamespace

from app.services import openkph_service


def setup_function() -> None:
    openkph_service.clear_cache()


def test_openkpl_limit_ladder_normalizes_daban_rows(monkeypatch):
    def fake_client_call(fn):
        class FakeClient:
            def get_daban_list(self, pid_type, date=None, count=500):  # noqa: ARG002
                kind = int(pid_type)
                if kind == 1:
                    return "2026-07-01", [
                        SimpleNamespace(
                            stock_id="000001",
                            name="平安银行",
                            change=10.0,
                            status="2连板",
                            plate="金融、银行",
                            seal=120000000,
                            price=12.5,
                            turnover=900000000,
                            turnover_ratio=3.2,
                            circ=10000000000,
                            reason="测试原因",
                            zt_time="09:35",
                            open_time="",
                        )
                    ]
                if kind == 2:
                    return "2026-07-01", [
                        SimpleNamespace(
                            stock_id="000002",
                            name="万科A",
                            change=8.8,
                            status="",
                            plate="地产",
                            seal=0,
                            price=8.2,
                            turnover=600000000,
                            turnover_ratio=4.1,
                            circ=8000000000,
                            reason="",
                            zt_time="10:10",
                            open_time="10:30",
                        )
                    ]
                return "2026-07-01", []

        return fn(FakeClient())

    monkeypatch.setattr(openkph_service, "_client_call", fake_client_call)

    payload = openkph_service.get_limit_ladder(direction="up")

    assert payload["source"] == "openkpl"
    assert payload["counts"] == {"up": 1, "down": 0}
    assert payload["tiers"][0]["boards"] == 2
    first = payload["tiers"][0]["stocks"][0]
    assert first["symbol"] == "000001"
    assert first["change_pct"] == 0.1
    assert first["openkpl__concept"] == "金融、银行"
    assert first["status"] == "limit_up"


def test_openkpl_plate_analysis_normalizes_rank_and_stock_rows(monkeypatch):
    def fake_client_call(fn):
        class FakeClient:
            def get_plate_ranking(self, category, order, count=36, date=None):  # noqa: ARG002
                return "2026-07-01", 1, [
                    SimpleNamespace(
                        plate_id="801001",
                        name="芯片",
                        strength=1200,
                        rise=5.5,
                        speed=0.2,
                        turnover=12300000000,
                        net_amount=300000000,
                        volume_ratio=1.8,
                        circ_mv=900000000000,
                    )
                ]

            def get_plate_stocks(self, plate_id, count=80, date=None):  # noqa: ARG002
                return "2026-07-01", 1, [
                    SimpleNamespace(
                        stock_id="603986",
                        name="兆易创新",
                        price=120.5,
                        rise=6.2,
                        turnover=2100000000,
                        turnover_rate=5.4,
                        real_turnover_rate=5.4,
                        volume_ratio=2.1,
                        total_mv=180000000000,
                        circ_mv=160000000000,
                        real_circ=160000000000,
                        board_desc="首板",
                        tag="龙一",
                        main_net=200000000,
                        main_buy=500000000,
                        main_sell=-300000000,
                        strength=1500,
                    )
                ]

        return fn(FakeClient())

    monkeypatch.setattr(openkph_service, "_client_call", fake_client_call)

    payload = openkph_service.get_plate_analysis("concept", rank_limit=1, stocks_per_plate=5)

    assert payload["source"] == "openkpl"
    assert payload["kind"] == "concept"
    assert payload["plates"][0]["name"] == "芯片"
    assert payload["plates"][0]["change_pct"] == 0.055
    assert payload["rows"][0]["concept"] == "芯片"
    assert payload["rows"][0]["symbol"] == "603986"
    assert payload["rows"][0]["change_pct"] == 0.062
    assert payload["rows"][0]["consecutive_limit_ups"] == 1
