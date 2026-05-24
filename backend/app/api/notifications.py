"""알림·캐시 브리핑·뉴스 요약 API."""
from fastapi import APIRouter
from pydantic import BaseModel

from app.scheduler.jobs import (
    get_unread_alerts,
    load_briefing_cache,
    load_news_cache,
    mark_alerts_read,
    save_briefing_cache,
)

router = APIRouter()


# ─── 알림 ─────────────────────────────────────────────────────────────────────

@router.get("/notifications/alerts")
def get_alerts():
    """읽지 않은 가격 알림 목록 반환."""
    return {"alerts": get_unread_alerts()}


class ReadRequest(BaseModel):
    ids: list[str]


@router.post("/notifications/alerts/read")
def mark_read(body: ReadRequest):
    """알림 읽음 처리."""
    mark_alerts_read(body.ids)
    return {"ok": True}


# ─── 캐시된 브리핑 ────────────────────────────────────────────────────────────

@router.get("/notifications/briefing-cache")
def get_briefing_cache():
    """오늘 캐시된 브리핑 반환. 없으면 null."""
    cached = load_briefing_cache()
    return {"cached": cached}


# ─── 개장 전 뉴스 요약 ────────────────────────────────────────────────────────

@router.get("/notifications/premarket-news")
def get_premarket_news():
    """오늘 개장 전 뉴스 요약 반환. 없으면 null."""
    cached = load_news_cache()
    return {"cached": cached}


@router.post("/notifications/premarket-news/generate")
def generate_premarket_news():
    """수동으로 개장 전 뉴스 요약 생성 (테스트용)."""
    from app.scheduler.jobs import job_premarket_news_summary
    job_premarket_news_summary()
    return {"cached": load_news_cache()}


@router.post("/notifications/briefing/generate")
def generate_briefing_now():
    """수동으로 브리핑 생성 + 캐시 저장 (테스트용)."""
    from app.api.portfolio import get_portfolio_briefing
    result = get_portfolio_briefing()
    save_briefing_cache(result)
    return {"cached": result}
