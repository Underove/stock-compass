from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.api.auth import get_current_user
from app.db.trade_db import get_profile, upsert_profile

router = APIRouter()

VALID_RISK = {"aggressive", "neutral", "defensive"}
VALID_HORIZON = {"short", "mid", "long"}
VALID_GOAL = {"growth", "income", "trading"}
VALID_EXPERIENCE = {"beginner", "intermediate", "expert"}
VALID_SECTORS = {
    "반도체", "2차전지·전기차", "바이오·제약", "자동차",
    "IT·플랫폼", "금융·보험", "게임·엔터", "화학·소재",
    "조선·방산", "소비재·유통", "건설·인프라", "에너지·유틸리티",
}


class ProfileIn(BaseModel):
    risk_level: str | None = None
    horizon: str | None = None
    sectors: list[str] | None = None
    goal: str | None = None
    experience: str | None = None

    @field_validator("goal")
    @classmethod
    def check_goal(cls, v):
        if v is not None and v not in VALID_GOAL:
            raise ValueError(f"goal은 {VALID_GOAL} 중 하나여야 합니다")
        return v

    @field_validator("experience")
    @classmethod
    def check_experience(cls, v):
        if v is not None and v not in VALID_EXPERIENCE:
            raise ValueError(f"experience는 {VALID_EXPERIENCE} 중 하나여야 합니다")
        return v

    @field_validator("risk_level")
    @classmethod
    def check_risk(cls, v):
        if v is not None and v not in VALID_RISK:
            raise ValueError(f"risk_level은 {VALID_RISK} 중 하나여야 합니다")
        return v

    @field_validator("horizon")
    @classmethod
    def check_horizon(cls, v):
        if v is not None and v not in VALID_HORIZON:
            raise ValueError(f"horizon은 {VALID_HORIZON} 중 하나여야 합니다")
        return v

    @field_validator("sectors")
    @classmethod
    def check_sectors(cls, v):
        if v is not None:
            if len(v) > 4:
                raise ValueError("섹터는 최대 4개까지 선택 가능합니다")
            invalid = [s for s in v if s not in VALID_SECTORS]
            if invalid:
                raise ValueError(f"유효하지 않은 섹터: {invalid}")
        return v


@router.get("/profile")
def get_user_profile(username: str = Depends(get_current_user)):
    return get_profile(username)


@router.put("/profile")
def update_user_profile(req: ProfileIn, username: str = Depends(get_current_user)):
    upsert_profile(username, req.risk_level, req.horizon, req.sectors, req.goal, req.experience)
    return get_profile(username)
