"""KIS (한국투자증권) OAuth 토큰 + 실시간 WebSocket 체결가 스트리밍."""
import json
import time
from pathlib import Path

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

# 토큰 파일: 서버 재시작해도 유효한 토큰 재사용
_TOKEN_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "kis_token.json"


def _load_token_file() -> None:
    """파일에서 토큰 읽어 메모리 캐시에 올림."""
    try:
        if _TOKEN_FILE.exists():
            data = json.loads(_TOKEN_FILE.read_text())
            if data.get("expires_at", 0) > time.time() + 60:
                _token_cache["token"] = data["token"]
                _token_cache["expires_at"] = data["expires_at"]
    except Exception:
        pass


def _save_token_file() -> None:
    """메모리 캐시 → 파일 저장."""
    try:
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN_FILE.write_text(json.dumps({
            "token": _token_cache["token"],
            "expires_at": _token_cache["expires_at"],
        }))
    except Exception:
        pass


_load_token_file()  # 모듈 로드 시 파일에서 복원


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
    _save_token_file()
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


# 지수 코드: 프론트 식별자 → (KIS TR_ID, KIS TR_KEY)
_INDEX_MAP = {
    "KOSPI":  ("H0UPCNT0", "0001"),
    "KOSDAQ": ("H0UPDNT0", "1001"),
}
_KIS_TO_INDEX = {"0001": "KOSPI", "1001": "KOSDAQ"}


def is_index_code(code: str) -> bool:
    return code in _INDEX_MAP


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


def subscribe_index_msg(approval_key: str, code: str) -> str:
    tr_id, tr_key = _INDEX_MAP[code]
    return json.dumps({
        "header": {
            "approval_key": approval_key,
            "custtype": "P",
            "tr_type": "1",
            "content-type": "utf-8",
        },
        "body": {"input": {"tr_id": tr_id, "tr_key": tr_key}},
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


def parse_index(raw: str) -> dict | None:
    """H0UPCNT0(KOSPI) / H0UPDNT0(KOSDAQ) 파이프 구분 응답 파싱."""
    if not raw.startswith("0|"):
        return None
    parts = raw.split("|", 3)
    if len(parts) < 4:
        return None
    tr_id = parts[1]
    if tr_id not in ("H0UPCNT0", "H0UPDNT0"):
        return None
    fields = parts[3].split("^")
    if len(fields) < 5:
        return None
    try:
        sign = fields[3]
        change_abs = float(fields[2])
        change_pct_abs = float(fields[4])
        display = _KIS_TO_INDEX.get(fields[0], fields[0])
        return {
            "stock_code": display,
            "time": "",
            "current_price": round(float(fields[1]), 2),
            "change_sign": sign,
            "change_amount": round(change_abs if sign in ("1", "2") else -change_abs if sign in ("4", "5") else 0.0, 2),
            "change_pct": round(change_pct_abs if sign in ("1", "2") else -change_pct_abs if sign in ("4", "5") else 0.0, 2),
            "volume": int(float(fields[5])) if len(fields) > 5 else 0,
            "is_index": True,
        }
    except (ValueError, IndexError):
        return None
