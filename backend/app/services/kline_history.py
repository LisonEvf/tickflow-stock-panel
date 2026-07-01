"""On-demand stock daily history loading.

The UI should be able to open a stock detail panel and see a usable historical
K-line even when the local parquet store only has today's live candle.  This
module keeps that rule in one place: read local enriched data first, and backfill
from OpenTDX when local coverage is too thin for the requested range.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta

import polars as pl

from app.indicators.pipeline import compute_enriched
from app.services import kline_sync

logger = logging.getLogger(__name__)


def _coverage_stats(df: pl.DataFrame) -> tuple[date | None, date | None]:
    if df.is_empty() or "date" not in df.columns:
        return None, None
    try:
        row = df.select(
            pl.col("date").min().alias("min_date"),
            pl.col("date").max().alias("max_date"),
        ).to_dicts()[0]
        return row.get("min_date"), row.get("max_date")
    except Exception:  # noqa: BLE001
        return None, None


def expected_min_rows(start: date, end: date, min_rows: int | None = None) -> int:
    """Approximate how many daily bars should exist in a range.

    We deliberately use a loose lower bound.  The goal is not perfect exchange
    calendar math; it is to catch obvious under-coverage such as one live candle
    for a six-month detail chart.
    """
    span_days = max((end - start).days + 1, 1)
    if min_rows is not None:
        return max(1, min_rows)
    if span_days < 21:
        return 1
    return min(500, max(20, int(span_days * 0.45)))


def should_backfill(local: pl.DataFrame, start: date, end: date, min_rows: int | None = None) -> bool:
    if local.is_empty():
        return True

    span_days = max((end - start).days + 1, 1)
    needed = expected_min_rows(start, end, min_rows=min_rows)
    if local.height < needed:
        return True

    first_date, last_date = _coverage_stats(local)
    if not first_date or not last_date:
        return False

    if span_days >= 30:
        start_slack = timedelta(days=min(30, max(7, span_days // 5)))
        if first_date > start + start_slack:
            return True

    if last_date < end - timedelta(days=10):
        return True

    return False


def _fetch_factors(symbol: str, capset) -> pl.DataFrame:
    if capset is None:
        return pl.DataFrame()
    try:
        from app.tickflow.capabilities import Cap

        if capset.has(Cap.ADJ_FACTOR):
            return kline_sync.fetch_adj_factor_single(symbol)
    except Exception as e:  # noqa: BLE001
        logger.debug("single symbol adj factor fetch failed %s: %s", symbol, e)
    return pl.DataFrame()


def _repo_instruments(repo) -> pl.DataFrame:
    try:
        return repo.get_instruments()
    except Exception:  # noqa: BLE001
        return pl.DataFrame()


def _fetch_opentdx_history(repo, symbol: str, start: date, end: date, capset) -> pl.DataFrame:
    fetch_start = start - timedelta(days=150)
    raw = kline_sync.sync_daily_batch(
        [symbol],
        start_time=datetime.combine(fetch_start, time.min),
        end_time=datetime.combine(end, time.max),
    )
    if raw.is_empty():
        return raw

    enriched = compute_enriched(
        raw,
        factors=_fetch_factors(symbol, capset),
        instruments=_repo_instruments(repo),
    )
    if enriched.is_empty() or "date" not in enriched.columns:
        return enriched
    return enriched.filter(
        (pl.col("date") >= start) & (pl.col("date") <= end),
    ).sort("date")


def load_daily_history(
    repo,
    symbol: str,
    start: date,
    end: date,
    *,
    capset=None,
    min_rows: int | None = None,
) -> tuple[pl.DataFrame, str]:
    """Load enriched daily history, backfilling from OpenTDX when needed.

    Returns ``(df, source)`` where source is ``enriched``, ``opentdx`` or
    ``none``.  If OpenTDX fails but local data exists, the local data is kept.
    """
    local = repo.get_daily(symbol, start, end)
    if not should_backfill(local, start, end, min_rows=min_rows):
        return local.sort("date") if "date" in local.columns else local, "enriched"

    try:
        opentdx_df = _fetch_opentdx_history(repo, symbol, start, end, capset)
    except Exception as e:  # noqa: BLE001
        logger.warning("OpenTDX daily history backfill failed for %s: %s", symbol, e)
        opentdx_df = pl.DataFrame()

    if not opentdx_df.is_empty():
        return opentdx_df, "opentdx"
    if not local.is_empty():
        return local.sort("date") if "date" in local.columns else local, "enriched"
    return pl.DataFrame(), "none"
