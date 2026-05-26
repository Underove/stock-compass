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
    per_min:        float | None = None
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
        per_min=req.per_min,
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
    username: str = Depends(get_current_user),
):
    """다중 지표 유사도 기반 추천 (재무·기술·공시·보유 종목 제외)."""
    from app.api.portfolio import _load as load_portfolio

    all_rows = query_screener(limit=5000)
    target = next((r for r in all_rows if r["stock_code"] == stock_code), None)
    if not target:
        raise HTTPException(status_code=404, detail="종목 없음")

    # 1) 보유 종목 제외 (하드 필터)
    owned = {i["stock_code"] for i in load_portfolio(username)}

    # 2) 후보군: 같은 섹터 우선, 5개 미만이면 전체로 확장
    candidates = [r for r in all_rows
                  if r["stock_code"] != stock_code and r["stock_code"] not in owned]
    same_sector = [r for r in candidates if r["sector"] == target["sector"]]
    pool = same_sector if len(same_sector) >= 5 else candidates

    if not pool:
        return []

    def _norm(vals_with_target: list[float]) -> list[float]:
        """마지막 원소가 타겟. None → 중간값(0.5) 대체 후 min-max 정규화."""
        clean = [v for v in vals_with_target if v is not None]
        if not clean or max(clean) == min(clean):
            return [0.5] * len(vals_with_target)
        mn, mx = min(clean), max(clean)
        rng = mx - mn
        return [(v - mn) / rng if v is not None else 0.5 for v in vals_with_target]

    # 3) 지표별 정규화 (pool 전체 + 타겟을 같은 스케일로)
    def col(key: str, fallback: float = 0.0) -> tuple[list[float], float]:
        vals = [r.get(key) or fallback for r in pool]
        t_val = target.get(key) or fallback
        normed = _norm(vals + [t_val])
        return normed[:-1], normed[-1]   # (pool_normed, target_normed)

    per_n,  t_per_n  = col("per",            0.0)  # 재무: PER
    pbr_n,  t_pbr_n  = col("pbr",            0.0)  # 재무: PBR
    mcap_n, t_mcap_n = col("market_cap",     0.0)  # 규모: 시가총액
    rsi_n,  t_rsi_n  = col("rsi",           50.0)  # 기술: RSI
    mom_n,  t_mom_n  = col("momentum_20d",   0.0)  # 기술: 20일 모멘텀
    disc_n, t_disc_n = col("disclosure_30d", 0.0)  # 공시 활동
    vol_n,  t_vol_n  = col("volume_ratio",   1.0)  # 최근 이슈: 거래량 급등
    fgn_n,  t_fgn_n  = col("foreign_net_buy", 0.0) # 최근 이슈: 외인·기관 순매수

    # 4) MA 방향 (같은 방향이면 보너스)
    t_ma = target.get("ma_status") or "none"
    t_bullish = t_ma in ("golden", "above")

    # 5) 가중 유클리드 거리 계산
    # 재무(PER·PBR): 35%, 규모(시총): 12%, 기술(RSI·모멘텀): 31%, 공시: 10%, 최근이슈(거래량·외인): 12%
    W = {"per": 0.20, "pbr": 0.15, "mcap": 0.12, "rsi": 0.18, "mom": 0.13,
         "disc": 0.10, "vol": 0.07, "fgn": 0.05}

    scored: list[tuple[float, dict]] = []
    for i, row in enumerate(pool):
        dist = math.sqrt(
            W["per"]  * (per_n[i]  - t_per_n)  ** 2 +
            W["pbr"]  * (pbr_n[i]  - t_pbr_n)  ** 2 +
            W["mcap"] * (mcap_n[i] - t_mcap_n) ** 2 +
            W["rsi"]  * (rsi_n[i]  - t_rsi_n)  ** 2 +
            W["mom"]  * (mom_n[i]  - t_mom_n)  ** 2 +
            W["disc"] * (disc_n[i] - t_disc_n) ** 2 +
            W["vol"]  * (vol_n[i]  - t_vol_n)  ** 2 +
            W["fgn"]  * (fgn_n[i]  - t_fgn_n)  ** 2
        )
        # MA 방향 일치 보너스
        row_ma = row.get("ma_status") or "none"
        if (row_ma in ("golden", "above")) == t_bullish:
            dist -= 0.04

        scored.append((dist, row))

    scored.sort(key=lambda x: x[0])
    return [row for _, row in scored[:8]]


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
