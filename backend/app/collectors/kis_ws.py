"""KIS (한국투자증권) OAuth 토큰 + 실시간 WebSocket 체결가 스트리밍."""
import json
import time

import httpx

from app.config import settings

_IS_MOCK = settings.kis_is_mock
_REST_BASE = (
    "https://openapivts.koreainvestment.com:29443"
    if _IS_MOCK
    else "https://openapi.koreainvestment.com:9443"
)
WS_URL = (
    "ws://ops.koreainvestment.com:31000"
    if _IS_MOCK
    else "ws://ops.koreainvestment.com:21000"
)

_token_cache: dict = {"token": "", "expires_at": 0.0}
_approval_cache: dict = {"key": "", "expires_at": 0.0}


def get_access_token() -> str:
    now = time.time()
    if _token_cache["token"] and _token_cache["expires_at"] > now + 60:
        return _token_cache["token"]
    with httpx.Client(timeout=10) as c:
        r = c.post(
            f"{_REST_BASE}/oauth2/tokenP",
            json={
                "grant_type": "client_credentials",
                "appkey": settings.kis_app_key,
                "appsecret": settings.kis_app_secret,
            },
        )
        r.raise_for_status()
        data = r.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = now + int(data.get("expires_in", 86400))
    return _token_cache["token"]


def get_approval_key() -> str:
    now = time.time()
    if _approval_cache["key"] and _approval_cache["expires_at"] > now + 60:
        return _approval_cache["key"]
    with httpx.Client(timeout=10) as c:
        r = c.post(
            f"{_REST_BASE}/oauth2/Approval",
            json={
                "grant_type": "client_credentials",
                "appkey": settings.kis_app_key,
                "secretkey": settings.kis_app_secret,
            },
        )
        r.raise_for_status()
        data = r.json()
    _approval_cache["key"] = data["approval_key"]
    _approval_cache["expires_at"] = now + 86400
    return _approval_cache["key"]


def subscribe_msg(approval_key: str, stock_code: str) -> str:
    return json.dumps({
        "header": {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8",
        },
        "body": {"input": {"tr_id": "H0STCNT0", "tr_key": stock_code}},
    })


def parse_price(raw: str) -> dict | None:
    """H0STCNT0 파이프 구분 응답 파싱. 실패 시 None."""
    # 데이터 형식: <구분>|<TR_ID>|<건수>|<데이터(^구분)>
    # 구분 0 = 실시간 데이터, 1 = 공통 응답
    if not raw.startswith("0|"):
        return None
    parts = raw.split("|", 3)
    if len(parts) < 4:
        return None
    fields = parts[3].split("^")
    if len(fields) < 13:
        return None
    try:
        sign = fields[3]  # 1=상한/2=상승/3=보합/4=하한/5=하락
        change_amount = int(fields[4])
        return {
            "stock_code": fields[0],
            "time": fields[1],
            "current_price": int(fields[2]),
            "change_sign": sign,
            "change_amount": change_amount if sign in ("1", "2") else -change_amount if sign in ("4", "5") else 0,
            "change_pct": float(fields[5]) if sign in ("1", "2") else -float(fields[5]) if sign in ("4", "5") else 0.0,
            "volume": int(fields[13]) if len(fields) > 13 else 0,
        }
    except (ValueError, IndexError):
        return None
