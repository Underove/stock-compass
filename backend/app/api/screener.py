# backend/app/api/screener.py
"""종목 스크리너 API."""
import json
import logging
import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.db.trade_db import (
    delete_filter,
    get_saved_filters,
    query_screener,
    save_filter,
)

router = APIRouter()
logger = logging.getLogger(__name__)


# ─── Request / Response 모델 ────────────────────────────────────────────────

class ScreenerRequest(BaseModel):
    sector:         str | None   = None
    market_cap_min: int | None   = None
    market_cap_max: int | None   = None
    per_max:        float | None = None
    pbr_max:        float | None = None
    rsi_min:        float | None = None
    rsi_max:        float | None = None
    ma_status:      str | None   = None


class SaveFilterRequest(ScreenerRequest):
    name: str


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────

@router.post("/screener")
def screen_stocks_endpoint(
    req: ScreenerRequest,
    _username: str = Depends(get_current_user),
):
    """조건 필터링 → 최대 50개 반환."""
    results = query_screener(
        sector=req.sector,
        market_cap_min=req.market_cap_min,
        market_cap_max=req.market_cap_max,
        per_max=req.per_max,
        pbr_max=req.pbr_max,
        rsi_min=req.rsi_min,
        rsi_max=req.rsi_max,
        ma_status=req.ma_status,
        limit=50,
    )
    return results


@router.get("/screener/similar/{stock_code}")
def similar_stocks(
    stock_code: str,
    _username: str = Depends(get_current_user),
):
    """타겟 종목과 유사한 5개 반환."""
    all_rows = query_screener(limit=5000)  # collector caps at 300 rows; 5000 is a safe upper bound
    target = next((r for r in all_rows if r["stock_code"] == stock_code), None)
    if not target:
        raise HTTPException(status_code=404, detail="종목 없음")

    # 같은 섹터로 1차 필터
    same_sector = [r for r in all_rows if r["sector"] == target["sector"] and r["stock_code"] != stock_code]
    if not same_sector:
        same_sector = [r for r in all_rows if r["stock_code"] != stock_code]

    def _norm_list(vals: list) -> list[float]:
        """None 제거 후 min-max 정규화. None은 0.5로 대체."""
        clean = [v for v in vals if v is not None]
        if not clean:
            return [0.0] * len(vals)
        mn, mx = min(clean), max(clean)
        rng = mx - mn or 1.0
        return [(v - mn) / rng if v is not None else 0.5 for v in vals]

    t_per  = target["per"]          or 0.0
    t_mcap = target["market_cap"]   or 0.0
    t_mom  = target["momentum_20d"] or 0.0

    # 타겟도 같은 스케일에 포함해서 min-max 정규화
    all_pers  = _norm_list([r["per"]                  for r in same_sector] + [t_per])
    all_mcaps = _norm_list([r["market_cap"]            for r in same_sector] + [t_mcap])
    all_moms  = _norm_list([r["momentum_20d"] or 0.0   for r in same_sector] + [t_mom])

    t_per_n  = all_pers[-1]
    t_mcap_n = all_mcaps[-1]
    t_mom_n  = all_moms[-1]

    scored: list[tuple[float, dict]] = []
    for i, row in enumerate(same_sector):
        dp  = all_pers[i]  - t_per_n
        dm  = all_mcaps[i] - t_mcap_n
        dmo = all_moms[i]  - t_mom_n
        dist = math.sqrt(dp * dp + dm * dm + dmo * dmo)
        scored.append((dist, row))

    scored.sort(key=lambda x: x[0])
    return [row for _, row in scored[:5]]


@router.get("/screener/filters")
def list_filters(username: str = Depends(get_current_user)):
    rows = get_saved_filters(username)
    return [
        {
            "id":          r["id"],
            "name":        r["name"],
            "params":      json.loads(r["filter_json"]),
            "created_at":  r["created_at"],
        }
        for r in rows
    ]


@router.post("/screener/filters")
def create_filter(req: SaveFilterRequest, username: str = Depends(get_current_user)):
    params = req.model_dump(exclude={"name"}, exclude_none=True)
    fid = save_filter(username, req.name, json.dumps(params, ensure_ascii=False))
    return {"id": fid, "name": req.name, "params": params}


@router.delete("/screener/filters/{filter_id}")
def remove_filter(filter_id: int, username: str = Depends(get_current_user)):
    deleted = delete_filter(filter_id, username)
    return {"deleted": deleted}
