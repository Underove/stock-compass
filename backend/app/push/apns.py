"""APNs(Apple Push Notification service) 토큰 방식 발송기.

설정(apns_key_p8/key_id/team_id)이 비어 있으면 모든 함수가 조용히 no-op이라,
키 없이도 알림 저장은 정상 동작한다(푸시만 skip). HTTP/2 전용이라 httpx[http2](h2) 필요.
"""
import json
import logging
import threading
import time

import httpx
import jwt  # PyJWT[crypto] — ES256 서명에 cryptography 사용

from app.config import settings
from app.db.trade_db import delete_device_token, get_device_tokens, get_unread_alerts

_log = logging.getLogger(__name__)

_PROD_HOST = "https://api.push.apple.com"
_SANDBOX_HOST = "https://api.sandbox.push.apple.com"

_token_lock = threading.Lock()
_cached = {"jwt": None, "iat": 0.0}

_client_lock = threading.Lock()
_client: httpx.Client | None = None


def _configured() -> bool:
    return bool(settings.apns_key_p8 and settings.apns_key_id and settings.apns_team_id)


def _provider_token() -> str | None:
    """APNs provider JWT. 최대 1시간 재사용 가능 — 50분마다 갱신."""
    if not _configured():
        return None
    now = time.time()
    with _token_lock:
        if _cached["jwt"] and now - _cached["iat"] < 50 * 60:
            return _cached["jwt"]
        key = settings.apns_key_p8.replace("\\n", "\n")  # env 변수의 "\n" 이스케이프 복원
        token = jwt.encode(
            {"iss": settings.apns_team_id, "iat": int(now)},
            key,
            algorithm="ES256",
            headers={"kid": settings.apns_key_id},
        )
        _cached["jwt"] = token
        _cached["iat"] = now
        return token


def _get_client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = httpx.Client(http2=True, timeout=10.0)
        return _client


def send_to_user(username: str, title: str, body: str, data: dict | None = None,
                 sound: str = "default") -> None:
    """유저의 모든 기기로 푸시. 미설정/토큰없음이면 no-op. 무효 토큰(410/BadDeviceToken)은 정리."""
    token = _provider_token()
    if token is None:
        return
    device_tokens = get_device_tokens(username)
    if not device_tokens:
        return

    try:
        badge = len(get_unread_alerts(username))
    except Exception:
        badge = None

    aps: dict = {"alert": {"title": title, "body": body}, "sound": sound}
    if badge is not None:
        aps["badge"] = badge
    payload: dict = {"aps": aps}
    if data:
        payload.update(data)
    content = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    host = _SANDBOX_HOST if settings.apns_use_sandbox else _PROD_HOST
    headers = {
        "authorization": f"bearer {token}",
        "apns-topic": settings.apns_bundle_id,
        "apns-push-type": "alert",
        "apns-priority": "10",
    }
    client = _get_client()
    for dt in device_tokens:
        try:
            resp = client.post(f"{host}/3/device/{dt}", content=content, headers=headers)
            if resp.status_code == 410 or (resp.status_code == 400 and "BadDeviceToken" in resp.text):
                delete_device_token(dt)
                _log.info("[APNs] 무효 토큰 정리: %s…", dt[:8])
            elif resp.status_code != 200:
                _log.warning("[APNs] 발송 실패 %s: %s", resp.status_code, resp.text[:200])
        except Exception as e:
            _log.warning("[APNs] 발송 예외: %s", e)
