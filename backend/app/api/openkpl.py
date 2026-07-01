"""OpenKPL/OpenKPH-backed realtime page APIs."""
from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from app.services.openkph_service import get_limit_ladder, get_plate_analysis

router = APIRouter(prefix="/api/openkpl", tags=["openkpl"])


@router.get("/limit-ladder")
def openkpl_limit_ladder(
    as_of: date | None = None,
    direction: Literal["up", "down"] = Query("up"),
    count: int = Query(500, ge=1, le=1000),
) -> dict:
    return get_limit_ladder(as_of=as_of, direction=direction, count=count)


@router.get("/plates/{kind}")
def openkpl_plate_analysis(
    kind: Literal["concept", "industry"],
    as_of: date | None = None,
    rank_limit: int = Query(36, ge=1, le=80),
    stocks_per_plate: int = Query(80, ge=1, le=200),
) -> dict:
    try:
        return get_plate_analysis(
            kind,
            rank_limit=rank_limit,
            stocks_per_plate=stocks_per_plate,
            as_of=as_of,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
