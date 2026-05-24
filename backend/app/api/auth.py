"""Google OAuth 세션 토큰 검증 (next-auth JWT → FastAPI)."""
import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer

from app.config import settings

router = APIRouter()
ALGORITHM = "HS256"
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    if not token:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    try:
        payload = pyjwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
        sub: str = payload.get("sub", "")
        if not sub:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰")
        return sub
    except pyjwt.PyJWTError:
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰")


@router.get("/auth/me")
def me(user: str = Depends(get_current_user)):
    return {"user": user}
