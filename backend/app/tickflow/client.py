"""OpenTDX client compatibility wrapper for legacy TickFlow call sites."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import math
from typing import Any, Iterable

from opentdx.const import ADJUST, CATEGORY, MARKET, PERIOD
from opentdx.tdxClient import TdxClient
from opentdx.utils.help import query_market


FREE_ENDPOINT = "opentdx://local"
PAID_ENDPOINT = "opentdx://local"


def _symbol_to_market_code(symbol: str) -> tuple[MARKET, str]:
    code, _, suffix = symbol.strip().upper().partition(".")
    if suffix == "SH":
        return MARKET.SH, code
    if suffix == "SZ":
        return MARKET.SZ, code
    if suffix == "BJ":
        return MARKET.BJ, code
    market = query_market(code)
    if market is None:
        return MARKET.SH, code
    return market, code


def _market_suffix(market: MARKET | int | None) -> str:
    try:
        m = MARKET(market)
    except Exception:  # noqa: BLE001
        m = market
    if m == MARKET.SZ:
        return "SZ"
    if m == MARKET.BJ:
        return "BJ"
    return "SH"


def _is_index_code(market: MARKET | int | None, code: str) -> bool:
    try:
        m = MARKET(market)
    except Exception:  # noqa: BLE001
        m = market
    code = str(code or "").strip()
    return (m == MARKET.SZ and code.startswith("399")) or (m == MARKET.SH and code.startswith("000"))


def _to_symbol(row: dict) -> str:
    code = str(row.get("code") or row.get("symbol") or "").strip().upper()
    if "." in code:
        return code
    return f"{code}.{_market_suffix(row.get('market'))}"


def _normalize_quote(row: dict) -> dict:
    last_price = row.get("last_price", row.get("close"))
    prev_close = row.get("prev_close", row.get("pre_close"))
    if last_price in (None, 0, 0.0) and prev_close not in (None, 0, 0.0):
        last_price = prev_close
    change_amount = None
    change_pct = None
    if last_price is not None and prev_close not in (None, 0):
        change_amount = float(last_price) - float(prev_close)
        change_pct = change_amount / float(prev_close)
    return {
        **row,
        "symbol": _to_symbol(row),
        "last_price": last_price,
        "prev_close": prev_close,
        "volume": row.get("volume", row.get("vol")),
        "change_amount": change_amount,
        "change_pct": change_pct,
        "ext": {
            "change_amount": change_amount,
            "change_pct": change_pct,
            "turnover_rate": row.get("turnover"),
        },
    }


def _period_from_tickflow(period: str) -> tuple[PERIOD, int]:
    normalized = (period or "1d").lower()
    if normalized in {"1d", "day", "daily"}:
        return PERIOD.DAILY, 1
    if normalized in {"1m", "min_1"}:
        return PERIOD.MIN_1, 1
    if normalized in {"5m", "min_5"}:
        return PERIOD.MIN_5, 1
    if normalized in {"15m", "min_15"}:
        return PERIOD.MIN_15, 1
    if normalized in {"30m", "min_30"}:
        return PERIOD.MIN_30, 1
    if normalized in {"60m", "min_60"}:
        return PERIOD.MIN_60, 1
    return PERIOD.DAILY, 1


class _ExchangeApi:
    def __init__(self, owner: "OpenTDXCompatClient") -> None:
        self._owner = owner

    def get_instruments(self, exchange: str, instrument_type: str = "stock") -> list[dict]:
        market = {"SZ": MARKET.SZ, "SH": MARKET.SH, "BJ": MARKET.BJ}.get(exchange.upper(), MARKET.SH)
        rows = self._owner._client.stock_list(market, count=0)
        out: list[dict] = []
        for row in rows or []:
            code = str(row.get("code") or "")
            if not code or not self._match_instrument_type(code, market, instrument_type):
                continue
            out.append({
                **row,
                "symbol": f"{code}.{_market_suffix(market)}",
                "code": code,
                "exchange": _market_suffix(market),
                "type": instrument_type,
                "ext": {
                    "listing_date": None,
                    "total_shares": None,
                    "float_shares": None,
                },
            })
        return out

    @staticmethod
    def _match_instrument_type(code: str, market: MARKET, instrument_type: str) -> bool:
        if instrument_type == "index":
            return (market == MARKET.SZ and code.startswith("399")) or (
                market == MARKET.SH and code.startswith("000")
            )
        if instrument_type == "etf":
            return code.startswith(("15", "16", "18", "50", "51", "52", "56", "58"))
        if market == MARKET.SZ:
            return code.startswith(("00", "30"))
        if market == MARKET.SH:
            return code.startswith(("60", "68"))
        if market == MARKET.BJ:
            return code.startswith(("43", "83", "87", "88", "92"))
        return False


class _QuotesApi:
    def __init__(self, owner: "OpenTDXCompatClient") -> None:
        self._owner = owner

    def get(self, symbols: list[str], **_: object) -> list[dict]:
        quote_pairs: list[tuple[MARKET, str]] = []
        index_symbols: list[str] = []
        for symbol in symbols:
            market, code = _symbol_to_market_code(symbol)
            if _is_index_code(market, code):
                index_symbols.append(f"{code}.{_market_suffix(market)}")
            else:
                quote_pairs.append((market, code))

        rows: list[dict] = []
        if quote_pairs:
            rows.extend(self._owner._client.stock_quotes(quote_pairs) or [])
        if index_symbols:
            rows.extend(self._owner._index_quotes_for(index_symbols))
        return [_normalize_quote(row) for row in rows]

    def get_by_symbols(self, symbols: list[str], **kwargs: object) -> list[dict]:
        return self.get(symbols, **kwargs)

    def get_by_universes(self, universes: list[str], **_: object) -> list[dict]:
        rows: list[dict] = []
        for universe in universes:
            if universe == "CN_Equity_A":
                rows.extend(self._owner._client.stock_quotes_list(CATEGORY.A, count=0))
            elif universe == "CN_Index":
                rows.extend(self._owner._index_quotes())
            elif universe == "CN_ETF":
                rows.extend(self._owner._etf_quotes())
        return [_normalize_quote(row) for row in rows]


class _KlinesApi:
    def __init__(self, owner: "OpenTDXCompatClient") -> None:
        self._owner = owner

    def get(self, symbol: str, period: str = "1d", count: int = 250, **_: object) -> list[dict]:
        market, code = _symbol_to_market_code(symbol)
        tdx_period, times = _period_from_tickflow(period)
        rows = self._owner._client.stock_kline(
            market,
            code,
            tdx_period,
            count=min(max(count, 1), 800),
            times=times,
            adjust=ADJUST.NONE,
        )
        return [{**row, "symbol": f"{code}.{_market_suffix(market)}"} for row in rows or []]

    def batch(self, symbols: list[str], period: str = "1d", count: int = 250, **kwargs: object) -> dict[str, list[dict]]:
        return {symbol: self.get(symbol, period=period, count=count, **kwargs) for symbol in symbols}

    def intraday(self, symbol: str, count: int = 240, **kwargs: object) -> list[dict]:
        return self.get(symbol, period="1m", count=count, **kwargs)

    def intraday_batch(self, symbols: list[str], count: int = 240, **kwargs: object) -> dict[str, list[dict]]:
        return {symbol: self.intraday(symbol, count=count, **kwargs) for symbol in symbols}

    def ex_factors(self, symbols: list[str], **_: object) -> dict[str, list[dict]]:  # noqa: ARG002
        return {}


class _DepthApi:
    def __init__(self, owner: "OpenTDXCompatClient") -> None:
        self._owner = owner

    def get(self, symbol: str) -> dict:
        market, code = _symbol_to_market_code(symbol)
        rows = self._owner._client.stock_quotes_detail(market, code)
        row = rows[0] if rows else {}
        return {**row, "symbol": symbol, "depth": row.get("handicap")}

    def batch(self, symbols: list[str]) -> list[dict]:
        return [self.get(symbol) for symbol in symbols]


def _finite_float(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _non_zero_float(value: object) -> float | None:
    out = _finite_float(value)
    if out in (None, 0.0):
        return None
    return out


def _amount_yuan(value: object) -> float | None:
    """OpenTDX finance amounts are reported in thousands of CNY."""
    out = _non_zero_float(value)
    return out * 1000 if out is not None else None


def _shares(value: object) -> float | None:
    """OpenTDX share counts are reported in ten-thousand-share units."""
    out = _non_zero_float(value)
    return out * 10000 if out is not None else None


def _tdx_date(value: object) -> str | None:
    try:
        raw = f"{int(value):08d}"  # type: ignore[arg-type]
        parsed = date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
    except (TypeError, ValueError):
        return None
    return parsed.isoformat()


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0.0):
        return None
    return numerator / denominator * 100


def _per_share(amount: float | None, share_count: float | None) -> float | None:
    if amount is None or share_count in (None, 0.0):
        return None
    return amount / share_count


class _FinancialsApi:
    """OpenTDX F10 finance snapshot adapter for legacy TickFlow financial calls."""

    def __init__(self, owner: "OpenTDXCompatClient") -> None:
        self._owner = owner
        self._finance_cache: dict[str, dict[str, Any] | None] = {}

    def metrics(self, symbols: Iterable[str], **_: object) -> dict[str, list[dict]]:
        return self._table(symbols, "metrics")

    def income(self, symbols: Iterable[str], **_: object) -> dict[str, list[dict]]:
        return self._table(symbols, "income")

    def balance_sheet(self, symbols: Iterable[str], **_: object) -> dict[str, list[dict]]:
        return self._table(symbols, "balance_sheet")

    def cash_flow(self, symbols: Iterable[str], **_: object) -> dict[str, list[dict]]:
        return self._table(symbols, "cash_flow")

    def _table(self, symbols: Iterable[str], table: str) -> dict[str, list[dict]]:
        out: dict[str, list[dict]] = {}
        for symbol in symbols:
            finance = self._finance_for(symbol)
            if not finance:
                continue
            record = self._map_record(finance, table)
            if record:
                out[symbol] = [record]
        return out

    def _finance_for(self, symbol: str) -> dict[str, Any] | None:
        normalized = symbol.strip().upper()
        if normalized in self._finance_cache:
            return self._finance_cache[normalized]

        market, code = _symbol_to_market_code(normalized)
        try:
            from opentdx.parser import quotation

            finance = self._owner._client.q_client().call(quotation.Finance(market, code))
        except Exception:  # noqa: BLE001
            finance = None

        self._finance_cache[normalized] = finance if isinstance(finance, dict) else None
        return self._finance_cache[normalized]

    def _base_record(self, finance: dict[str, Any]) -> dict[str, Any]:
        report_date = _tdx_date(finance.get("updated_date"))
        return {
            "period_end": report_date,
            "announce_date": report_date,
            "source": "opentdx_f10",
        }

    def _derived(self, finance: dict[str, Any]) -> dict[str, float | None]:
        total_assets = _amount_yuan(finance.get("ZiChanZongJi"))
        equity = _amount_yuan(finance.get("GuiMuQuanYiHeJi"))
        liabilities = total_assets - equity if total_assets is not None and equity is not None and total_assets >= equity else None
        revenue = _amount_yuan(finance.get("YinYeZongShouRu"))
        operating_cost = _amount_yuan(finance.get("YinYeChengBen"))
        net_income = _amount_yuan(finance.get("ShuiHouLiRun"))
        net_income_attributable = _amount_yuan(finance.get("GuiMuJinLiRun"))
        operating_cash_flow = _amount_yuan(finance.get("JingYinXianJinLiuJinE"))
        inventory = _amount_yuan(finance.get("CunHuo"))
        total_shares = _shares(finance.get("zongguben"))
        return {
            "total_assets": total_assets,
            "equity": equity,
            "liabilities": liabilities,
            "revenue": revenue,
            "operating_cost": operating_cost,
            "net_income": net_income,
            "net_income_attributable": net_income_attributable,
            "operating_cash_flow": operating_cash_flow,
            "inventory": inventory,
            "total_shares": total_shares,
        }

    def _map_record(self, finance: dict[str, Any], table: str) -> dict[str, Any]:
        base = self._base_record(finance)
        d = self._derived(finance)
        if table == "metrics":
            gross_profit = (
                d["revenue"] - d["operating_cost"]
                if d["revenue"] is not None and d["operating_cost"] is not None
                else None
            )
            return {
                **base,
                "eps_basic": _finite_float(finance.get("MeiGuShouYi")),
                "eps_diluted": _finite_float(finance.get("MeiGuShouYi")),
                "bps": _finite_float(finance.get("MeiGuJinZiChan")),
                "ocfps": _per_share(d["operating_cash_flow"], d["total_shares"]),
                "roe": _pct(d["net_income_attributable"], d["equity"]),
                "roe_diluted": _pct(d["net_income_attributable"], d["equity"]),
                "roa": _pct(d["net_income"], d["total_assets"]),
                "gross_margin": _pct(gross_profit, d["revenue"]),
                "net_margin": _pct(d["net_income"], d["revenue"]),
                "debt_to_asset_ratio": _pct(d["liabilities"], d["total_assets"]),
                "revenue_yoy": None,
                "net_income_yoy": None,
                "operating_cash_to_revenue": _pct(d["operating_cash_flow"], d["revenue"]),
                "inventory_turnover": (
                    d["operating_cost"] / d["inventory"]
                    if d["operating_cost"] is not None and d["inventory"] not in (None, 0.0)
                    else None
                ),
            }
        if table == "income":
            return {
                **base,
                "revenue": d["revenue"],
                "operating_cost": d["operating_cost"],
                "operating_profit": _amount_yuan(finance.get("YinYeLiRun")),
                "investment_income": _amount_yuan(finance.get("TouZiShouYi")),
                "total_profit": _amount_yuan(finance.get("LiRunZongE")),
                "net_income": d["net_income"],
                "net_income_attributable": d["net_income_attributable"],
                "net_income_deducted": None,
                "basic_eps": _finite_float(finance.get("MeiGuShouYi")),
                "diluted_eps": _finite_float(finance.get("MeiGuShouYi")),
            }
        if table == "balance_sheet":
            return {
                **base,
                "total_assets": d["total_assets"],
                "total_current_assets": _amount_yuan(finance.get("LiuDongZiChanZongJi")),
                "cash_and_equivalents": None,
                "accounts_receivable": _amount_yuan(finance.get("YingShouZhangKuan")),
                "inventory": d["inventory"],
                "fixed_assets": _amount_yuan(finance.get("GuDingZiChanJinE")),
                "intangible_assets": _amount_yuan(finance.get("WuXingZiChan")),
                "total_liabilities": d["liabilities"],
                "total_current_liabilities": _amount_yuan(finance.get("LiuDongFuZhaiHeJi")),
                "long_term_borrowing": _amount_yuan(finance.get("changqifuzhai")),
                "total_equity": d["equity"],
                "equity_attributable": d["equity"],
                "capital_reserve": _amount_yuan(finance.get("ZiBenGongJiJin")),
                "retained_earnings": _amount_yuan(finance.get("WeiFenLiRun")),
                "total_shares": d["total_shares"],
                "float_shares": _shares(finance.get("liutongguben")),
                "shareholder_count": _finite_float(finance.get("GuDongRenShu")),
            }
        if table == "cash_flow":
            return {
                **base,
                "net_operating_cash_flow": d["operating_cash_flow"],
                "net_investing_cash_flow": None,
                "net_financing_cash_flow": None,
                "capex": None,
                "net_cash_change": _amount_yuan(finance.get("zongxianjinliu")),
                "total_cash_inflow": _amount_yuan(finance.get("zongxianjinliu")),
            }
        return {}


@dataclass
class OpenTDXCompatClient:
    _client: TdxClient

    def __post_init__(self) -> None:
        self._ensure_connected()
        self.exchanges = _ExchangeApi(self)
        self.quotes = _QuotesApi(self)
        self.klines = _KlinesApi(self)
        self.depth = _DepthApi(self)
        self.financials = _FinancialsApi(self)

    def _ensure_connected(self) -> None:
        client = self._client.q_client()
        if not client.connected:
            client.connect().login()

    def _index_quotes(self) -> list[dict]:
        return self._index_quotes_for(["000001.SH", "399001.SZ", "399006.SZ", "000680.SH"])

    def _index_quotes_for(self, symbols: list[str]) -> list[dict]:
        pairs = [_symbol_to_market_code(symbol) for symbol in symbols]
        rows = self._client.index_info(pairs) or []
        return [self._repair_index_quote(row) for row in rows]

    def _repair_index_quote(self, row: dict) -> dict:
        close = row.get("close")
        try:
            close_value = float(close)
        except (TypeError, ValueError):
            close_value = 0.0
        if close_value != 0:
            return row

        symbol = _to_symbol(row)
        daily = self._latest_daily_quote(symbol)
        return {**row, **daily} if daily else row

    def _latest_daily_quote(self, symbol: str) -> dict:
        market, code = _symbol_to_market_code(symbol)
        try:
            rows = self._client.stock_kline(
                market,
                code,
                PERIOD.DAILY,
                count=3,
                times=1,
                adjust=ADJUST.NONE,
            ) or []
        except Exception:  # noqa: BLE001
            return {}

        for i in range(len(rows) - 1, -1, -1):
            row = rows[i]
            try:
                close = float(row.get("close"))
            except (TypeError, ValueError):
                continue
            if close == 0:
                continue

            prev_close = None
            for prev in reversed(rows[:i]):
                try:
                    prev_close = float(prev.get("close"))
                except (TypeError, ValueError):
                    continue
                if prev_close != 0:
                    break
            return {
                "market": market,
                "code": code,
                "pre_close": prev_close,
                "close": close,
                "open": row.get("open") or close,
                "high": row.get("high") or close,
                "low": row.get("low") or close,
                "vol": row.get("vol", row.get("volume")),
                "amount": row.get("amount"),
            }
        return {}

    def _etf_quotes(self) -> list[dict]:
        symbols: list[str] = []
        for market in (MARKET.SH, MARKET.SZ):
            rows = self._client.stock_list(market, count=0)
            for row in rows or []:
                code = str(row.get("code") or "")
                if _ExchangeApi._match_instrument_type(code, market, "etf"):
                    symbols.append(f"{code}.{_market_suffix(market)}")
        return self.quotes.get(symbols[:500]) if symbols else []


_sync_client: OpenTDXCompatClient | None = None


def get_client() -> OpenTDXCompatClient:
    global _sync_client
    if _sync_client is None:
        _sync_client = OpenTDXCompatClient(TdxClient())
    return _sync_client


def get_async_client() -> OpenTDXCompatClient:
    return get_client()


def get_paid_realtime_client() -> OpenTDXCompatClient:
    return get_client()


def reset_clients() -> None:
    global _sync_client
    _sync_client = None


def current_mode() -> str:
    return "opentdx"


def current_endpoint() -> str:
    return FREE_ENDPOINT
