"""KIS REST API — 현재가 + 재무지표 조회 (실전/모의 공용, pykrx 대체)."""
from datetime import datetime, timedelta, timezone

import httpx

from app.collectors.kis_ws import get_access_token
from app.config import settings

_KST = timezone(timedelta(hours=9))

_REST_BASE = (
    "https://openapivts.koreainvestment.com:29443"
    if settings.kis_is_mock
    else "https://openapi.koreainvestment.com:9443"
)


def _session_from_kst(kst: datetime) -> str:
    if kst.weekday() >= 5:
        return "closed"
    total = kst.hour * 60 + kst.minute
    if 8 * 60 <= total < 9 * 60:
        return "pre"
    if 9 * 60 <= total < 15 * 60 + 30:
        return "open"
    if 15 * 60 + 30 <= total < 18 * 60:
        return "after"
    return "closed"


def _inquire_price(stock_code: str) -> dict:
    """FHKST01010100 호출 → output dict 반환. (소문자 키)"""
    token = get_access_token()
    r = httpx.get(
        f"{_REST_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": "FHKST01010100",
        },
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": stock_code},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("output", {})


def get_current_price_kis(stock_code: str) -> dict:
    """KIS REST로 현재가 조회. session 필드 포함."""
    out = _inquire_price(stock_code)

    kst = datetime.now(_KST)
    session = _session_from_kst(kst)

    # KIS 응답 키는 소문자
    regular_price = int(out.get("stck_prpr") or 0)
    after_price = int(out.get("ovtm_untp_prpr") or 0)
    ref_price = int(out.get("stck_sdpr") or 0)  # 기준가(전일종가 대용)

    if session == "after" and after_price > 0:
        current_price = after_price
        change_amount = int(out.get("ovtm_untp_prdy_vrss") or 0)
        change_pct = float(out.get("ovtm_untp_prdy_ctrt") or 0)
    elif regular_price > 0:
        current_price = regular_price
        change_amount = int(out.get("prdy_vrss") or 0)
        change_pct = float(out.get("prdy_ctrt") or 0)
    else:
        current_price = ref_price
        change_amount = int(out.get("prdy_vrss") or 0)
        change_pct = float(out.get("prdy_ctrt") or 0)

    return {
        "stock_code": stock_code,
        "current_price": current_price,
        "change_pct": change_pct,
        "change_amount": change_amount,
        "open": int(out.get("stck_oprc") or 0),
        "high": int(out.get("stck_hgpr") or 0),
        "low": int(out.get("stck_lwpr") or 0),
        "volume": int(out.get("acml_vol") or 0),
        "date": kst.strftime("%Y-%m-%d"),
        "session": session,
    }


def get_fundamental_kis(stock_code: str) -> dict:
    """KIS REST로 PER/PBR/EPS/BPS/시가총액 조회."""

    def pos(v) -> float | None:
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    try:
        out = _inquire_price(stock_code)
        # hts_avls 단위: 억원
        avls = out.get("hts_avls")
        market_cap = int(float(avls) * 1e8) if avls else None
        return {
            "per": pos(out.get("per")),
            "pbr": pos(out.get("pbr")),
            "eps": pos(out.get("eps")),
            "bps": pos(out.get("bps")),
            "div": None,  # KIS inquire-price에는 배당수익률 없음
            "market_cap": market_cap,
        }
    except Exception:
        return {"per": None, "pbr": None, "eps": None, "bps": None, "div": None, "market_cap": None}
