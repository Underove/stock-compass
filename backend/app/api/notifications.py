"""알림·캐시 브리핑·뉴스 요약 API."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.db.trade_db import (
    get_unread_alerts,
    mark_alerts_read,
    delete_alert,
    get_alert_watch,
    add_alert_watch,
    remove_alert_watch,
)
from app.scheduler.jobs import load_briefing_cache, load_news_cache, save_briefing_cache

router = APIRouter()


# ─── 알림 ─────────────────────────────────────────────────────────────────────

@router.get("/notifications/alerts")
def get_alerts(username: str = Depends(get_current_user)):
    """읽지 않은 알림 목록 반환 (유저별)."""
    return {"alerts": get_unread_alerts(username)}


class ReadRequest(BaseModel):
    ids: list[str]


@router.post("/notifications/alerts/read")
def mark_read(body: ReadRequest, username: str = Depends(get_current_user)):
    mark_alerts_read(username, body.ids)
    return {"ok": True}


@router.delete("/notifications/alerts/{alert_id}")
def remove_alert(alert_id: str, username: str = Depends(get_current_user)):
    """개별 알림 삭제."""
    deleted = delete_alert(username, alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
    return {"ok": True}


# ─── 모니터링 종목 ────────────────────────────────────────────────────────────

class WatchItem(BaseModel):
    stock_code: str
    corp_name: str


@router.get("/notifications/watch")
def list_watch(username: str = Depends(get_current_user)):
    return {"items": get_alert_watch(username)}


@router.post("/notifications/watch")
def add_watch(item: WatchItem, username: str = Depends(get_current_user)):
    add_alert_watch(username, item.stock_code, item.corp_name)
    return {"ok": True}


@router.delete("/notifications/watch/{stock_code}")
def remove_watch(stock_code: str, username: str = Depends(get_current_user)):
    remove_alert_watch(username, stock_code)
    return {"ok": True}


# ─── 캐시된 브리핑 ────────────────────────────────────────────────────────────

@router.get("/notifications/briefing-cache")
def get_briefing_cache():
    cached = load_briefing_cache()
    return {"cached": cached}


# ─── 개장 전 뉴스 요약 ────────────────────────────────────────────────────────

@router.get("/notifications/premarket-news")
def get_premarket_news():
    cached = load_news_cache()
    return {"cached": cached}


@router.post("/notifications/premarket-news/generate")
def generate_premarket_news():
    from app.scheduler.jobs import job_premarket_news_summary
    job_premarket_news_summary()
    return {"cached": load_news_cache()}


@router.post("/notifications/briefing/generate")
def generate_briefing_now():
    from app.api.portfolio import get_portfolio_briefing
    result = get_portfolio_briefing()
    save_briefing_cache(result)
    return {"cached": result}
