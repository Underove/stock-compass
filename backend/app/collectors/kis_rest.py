"""KIS REST API — 현재가 조회 (실전/모의 공용, pykrx 대체)."""
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


def get_current_price_kis(stock_code: str) -> dict:
    """KIS REST로 현재가 조회. session 필드 포함."""
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
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        },
        timeout=10,
    )
    r.raise_for_status()
    out = r.json().get("output", {})

    kst = datetime.now(_KST)
    return {
        "stock_code": stock_code,
        "current_price": int(out.get("STCK_PRPR") or 0),
        "change_pct": float(out.get("PRDY_CTRT") or 0),
        "change_amount": int(out.get("PRDY_VRSS") or 0),
        "open": int(out.get("STCK_OPRC") or 0),
        "high": int(out.get("STCK_HGPR") or 0),
        "low": int(out.get("STCK_LWPR") or 0),
        "volume": int(out.get("ACML_VOL") or 0),
        "date": kst.strftime("%Y-%m-%d"),
        "session": _session_from_kst(kst),
    }
