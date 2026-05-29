"""기기 푸시 토큰 등록 — APNs 발송 대상."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.config import settings
from app.db.trade_db import delete_device_token, get_device_tokens, upsert_device_token

router = APIRouter()


class DeviceIn(BaseModel):
    token: str
    platform: str = "ios"


@router.post("/devices")
def register_device(body: DeviceIn, username: str = Depends(get_current_user)):
    """앱이 받은 APNs 기기 토큰을 등록(upsert)."""
    upsert_device_token(username, body.token, body.platform)
    return {"ok": True}


@router.delete("/devices/{token}")
def unregister_device(token: str, username: str = Depends(get_current_user)):
    """로그아웃 등에서 토큰 해제."""
    delete_device_token(token)
    return {"ok": True}


@router.post("/devices/test")
def test_push(username: str = Depends(get_current_user)):
    """셋업 검증용 — 내 기기로 테스트 푸시 즉시 발송.
    devices=등록된 기기 수, configured=APNs 키 설정 여부."""
    from app.push.apns import send_to_user

    configured = bool(settings.apns_key_p8 and settings.apns_key_id and settings.apns_team_id)
    tokens = get_device_tokens(username)
    send_to_user(username, title="NOVA", body="테스트 푸시예요. 알림이 잘 도착했어요.",
                 data={"type": "test"})
    return {"ok": True, "devices": len(tokens), "configured": configured}
