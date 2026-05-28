"""모바일(iOS) 소셜 로그인 → 앱 JWT 발급.

웹 next-auth와 독립된 additive 엔드포인트. 제공자(Google/Apple) 토큰을 검증한 뒤
기존 get_current_user(app/api/auth.py)가 받는 것과 동일한 HS256 JWT(sub=email)를 발급.
client ID / bundle ID 미설정 시 503으로 비활성 — 웹/기존 동작에 영향 없음.
"""
import jwt as pyjwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

router = APIRouter()

ALGORITHM = "HS256"
APPLE_JWKS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"


def _issue_app_token(email: str) -> dict:
    """기존 백엔드 인증과 호환되는 앱 JWT 발급 (sub=email)."""
    token = pyjwt.encode({"sub": email}, settings.jwt_secret, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer"}


class GoogleTokenIn(BaseModel):
    id_token: str


@router.post("/auth/google-mobile")
def google_mobile(body: GoogleTokenIn):
    """iOS GoogleSignIn ID 토큰 검증 → 앱 JWT 발급."""
    if not settings.google_ios_client_id:
        raise HTTPException(503, "모바일 Google 로그인이 아직 설정되지 않았어요")

    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token as google_id_token

    try:
        info = google_id_token.verify_oauth2_token(
            body.id_token, google_requests.Request(), settings.google_ios_client_id
        )
    except Exception:
        raise HTTPException(401, "유효하지 않은 Google 토큰")

    email = info.get("email")
    if not email or info.get("email_verified") is False:
        raise HTTPException(401, "이메일을 확인할 수 없어요")
    return _issue_app_token(email)


class AppleTokenIn(BaseModel):
    identity_token: str
    email: str | None = None  # Apple은 최초 1회만 email 제공 → 앱이 보관했다가 전달


_apple_jwk_client = None


def _get_apple_jwk_client():
    global _apple_jwk_client
    if _apple_jwk_client is None:
        from jwt import PyJWKClient
        _apple_jwk_client = PyJWKClient(APPLE_JWKS_URL)
    return _apple_jwk_client


@router.post("/auth/apple-mobile")
def apple_mobile(body: AppleTokenIn):
    """Sign in with Apple identity 토큰 검증 → 앱 JWT 발급.

    주의: Apple은 재로그인 시 email을 안 줄 수 있음. 앱이 최초 email을 보관해
    body.email로 전달하거나, 추후 sub→email 매핑 테이블이 필요할 수 있음.
    """
    if not settings.apple_bundle_id:
        raise HTTPException(503, "모바일 Apple 로그인이 아직 설정되지 않았어요")

    try:
        signing_key = _get_apple_jwk_client().get_signing_key_from_jwt(body.identity_token)
        claims = pyjwt.decode(
            body.identity_token, signing_key.key, algorithms=["RS256"],
            audience=settings.apple_bundle_id, issuer=APPLE_ISSUER,
        )
    except Exception:
        raise HTTPException(401, "유효하지 않은 Apple 토큰")

    email = claims.get("email") or body.email
    if not email:
        raise HTTPException(400, "이메일이 필요해요. 최초 로그인 정보를 다시 확인해주세요")
    return _issue_app_token(email)
