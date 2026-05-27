"""KOSPI / KOSDAQ 실시간 지수 + 장 상태."""
import datetime
import logging
import time

import httpx
from fastapi import APIRouter
from fastapi.responses import Response

logger = logging.getLogger(__name__)

router = APIRouter()

_NAVER_CODES = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ"}
_NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": "https://finance.naver.com/",
}

# 5초 캐시 — Naver API 과부하 방지
_indices_cache: dict = {}
_indices_cache_ts: float = 0.0
_CACHE_TTL = 5.0


_KST = datetime.timezone(datetime.timedelta(hours=9))


def _now_kst() -> datetime.datetime:
    return datetime.datetime.now(_KST)


def _get_market_status() -> dict:
    """한국 주식시장 개폐장 상태 (KST 기준)."""
    now = _now_kst()
    weekday = now.weekday()  # 0=월, 6=일
    minutes = now.hour * 60 + now.minute

    if weekday >= 5:
        return {"status": "closed", "label": "주말 휴장"}
    if minutes < 8 * 60:
        return {"status": "closed", "label": "장 마감"}
    if minutes < 9 * 60:
        return {"status": "pre", "label": "장 개장 전"}
    if minutes < 15 * 60 + 30:
        return {"status": "open", "label": "장 운영 중"}
    if minutes < 18 * 60:
        return {"status": "after", "label": "시간외 거래"}
    return {"status": "closed", "label": "장 마감"}


def _fetch_indices_fresh() -> dict:
    """Naver API에서 지수 데이터 직접 조회."""
    indices: dict = {}
    for name, code in _NAVER_CODES.items():
        try:
            r = httpx.get(
                f"https://m.stock.naver.com/api/index/{code}/basic",
                headers=_NAVER_HEADERS,
                timeout=5,
            )
            r.raise_for_status()
            d = r.json()
            close = float(str(d.get("closePrice", "0")).replace(",", ""))
            change_abs = float(str(d.get("compareToPreviousClosePrice", "0")).replace(",", ""))
            ratio = float(str(d.get("fluctuationsRatio", "0")).replace(",", ""))
            trend = (d.get("compareToPreviousPrice") or {}).get("name", "RISING")
            sign = -1 if trend in ("FALLING", "DECLINE") else 1
            indices[name] = {
                "name": name,
                "value": round(close, 2),
                "change": round(sign * change_abs, 2),
                "change_pct": round(sign * ratio, 2),
            }
        except Exception as e:
            logger.warning("지수 조회 실패 (%s): %s", name, e)
    return indices


@router.get("/market/indices")
def get_market_indices():
    """KOSPI·KOSDAQ 지수값 + 장 상태 반환 (5초 캐시)."""
    global _indices_cache, _indices_cache_ts
    now = time.monotonic()
    if not _indices_cache or now - _indices_cache_ts > _CACHE_TTL:
        fresh = _fetch_indices_fresh()
        if fresh:
            _indices_cache = fresh
            _indices_cache_ts = now
    return {"indices": _indices_cache, "market_status": _get_market_status()}


_logo_cache: dict[str, bytes] = {}

@router.get("/stock/logo/{code}")
async def get_stock_logo(code: str):
    if code in _logo_cache:
        return Response(content=_logo_cache[code], media_type="image/png")
    url = f"https://static.toss.im/png-icons/securities/icod-krx-{code}.png"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            _logo_cache[code] = r.content
            return Response(content=r.content, media_type="image/png")
    except Exception:
        pass
    return Response(status_code=404)
