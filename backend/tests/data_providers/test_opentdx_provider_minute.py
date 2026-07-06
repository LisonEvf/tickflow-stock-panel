from datetime import date, datetime, time, timedelta

from app.data_providers.opentdx_provider import OpenTDXProvider


SYMBOL = "000001.SZ"


def _provider_with_client(client) -> OpenTDXProvider:
    provider = object.__new__(OpenTDXProvider)
    provider._client = client
    return provider


def _minute_rows(day: date, count: int = 245, price: float = 10.0) -> list[dict]:
    base = datetime.combine(day, time(9, 25))
    return [
        {
            "datetime": base + timedelta(minutes=i),
            "open": price,
            "high": price + 0.1,
            "low": price - 0.1,
            "close": price + i * 0.001,
            "vol": 1000 + i,
            "amount": 100000 + i,
        }
        for i in range(count)
    ]


def test_minute_fetch_pages_until_historical_target_day():
    target = date(2026, 7, 1)
    newer_base = datetime(2026, 7, 2, 9, 25)
    newer_page = [
        {
            "datetime": newer_base + timedelta(minutes=i),
            "open": 11,
            "high": 11.1,
            "low": 10.9,
            "close": 11,
            "vol": 1000,
            "amount": 100000,
        }
        for i in range(800)
    ]

    class FakeClient:
        def __init__(self):
            self.calls: list[dict] = []

        def stock_kline(self, market, code, period, start=0, count=800, adjust=None):
            self.calls.append({"start": start, "count": count})
            if start == 0:
                return newer_page
            if start == 800:
                return _minute_rows(target)
            return []

    client = FakeClient()
    provider = _provider_with_client(client)

    df = provider.get_minute(
        [SYMBOL],
        datetime(2026, 7, 1, 9, 25),
        datetime(2026, 7, 1, 15, 5),
        asset_type="stock",
        freq="1m",
    )

    assert [c["start"] for c in client.calls] == [0, 800]
    assert not df.is_empty()
    assert df["datetime"].dt.date().unique().to_list() == [target]
    assert df.height == 245


def test_minute_falls_back_to_historical_tick_chart_when_kline_empty():
    target = date(2026, 7, 1)

    class FakeClient:
        def __init__(self):
            self.tick_dates: list[date] = []

        def stock_kline(self, market, code, period, start=0, count=800, adjust=None):
            return []

        def stock_tick_chart(self, market, code, date=None):
            self.tick_dates.append(date)
            return [
                {"time": time(9, 30), "price": 10.0, "avg": 10.0, "vol": 100},
                {"time": time(9, 31), "price": 10.2, "avg": 10.12, "vol": 250},
            ]

    client = FakeClient()
    provider = _provider_with_client(client)

    df = provider.get_minute(
        [SYMBOL],
        datetime(2026, 7, 1, 9, 25),
        datetime(2026, 7, 1, 15, 5),
        asset_type="stock",
        freq="1m",
    )

    assert client.tick_dates == [target]
    assert not df.is_empty()
    assert df.select("datetime", "open", "high", "low", "close", "volume").to_dicts() == [
        {
            "datetime": datetime(2026, 7, 1, 9, 30),
            "open": 10.0,
            "high": 10.0,
            "low": 10.0,
            "close": 10.0,
            "volume": 100.0,
        },
        {
            "datetime": datetime(2026, 7, 1, 9, 31),
            "open": 10.2,
            "high": 10.2,
            "low": 10.2,
            "close": 10.2,
            "volume": 150.0,
        },
    ]
