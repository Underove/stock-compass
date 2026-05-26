import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from app.api import auth as auth_api  # noqa: E402
from app.api import analyze as analyze_api  # noqa: E402
from app.api import ask as ask_api  # noqa: E402
from app.api import dart as dart_api  # noqa: E402
from app.api import factcheck as factcheck_api  # noqa: E402
from app.api import market as market_api  # noqa: E402
from app.api import portfolio as portfolio_api  # noqa: E402
from app.api import realtime as realtime_api  # noqa: E402
from app.api import technical as technical_api  # noqa: E402
from app.api import search as search_api  # noqa: E402
from app.api import upload as upload_api  # noqa: E402
from app.api import notifications as notifications_api  # noqa: E402
from app.api import watchlist as watchlist_api  # noqa: E402
from app.api import trades as trades_api  # noqa: E402
from app.api import profile as profile_api  # noqa: E402
from app.api import screener as screener_api  # noqa: E402
from app.api import compare as compare_api  # noqa: E402
from app.config import settings  # noqa: E402
from app.db.trade_db import init_db  # noqa: E402
from app.scheduler.jobs import (  # noqa: E402
    job_check_price_alerts,
    job_generate_briefing,
    job_premarket_news_summary,
    job_save_portfolio_snapshots,
    job_refresh_screener_fundamentals,
    job_refresh_screener_ta,
    job_refresh_screener_market_signals,
    job_refresh_disclosure_counts,
    job_check_dart_alerts,
    job_check_volume_alerts,
    job_check_technical_alerts,
)

KST = "Asia/Seoul"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = BackgroundScheduler(timezone=KST)
    # 장 마감 자동 브리핑 (평일 15:35 KST)
    scheduler.add_job(job_generate_briefing, CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=KST))
    # 목표가·손절가 알림 (평일 장 중 매 5분)
    scheduler.add_job(job_check_price_alerts, CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/5", timezone=KST))
    # 개장 전 뉴스 요약 (평일 08:50 KST)
    scheduler.add_job(job_premarket_news_summary, CronTrigger(day_of_week="mon-fri", hour=8, minute=50, timezone=KST))
    # 포트폴리오 스냅샷 (평일 15:32 KST)
    scheduler.add_job(job_save_portfolio_snapshots, CronTrigger(day_of_week="mon-fri", hour=15, minute=32, timezone=KST))
    # 스크리너 기본 지표 갱신 (평일 16:10 KST)
    scheduler.add_job(job_refresh_screener_fundamentals, CronTrigger(day_of_week="mon-fri", hour=16, minute=10, timezone=KST))
    # 스크리너 TA 배치 (평일 16:20 KST)
    scheduler.add_job(job_refresh_screener_ta, CronTrigger(day_of_week="mon-fri", hour=16, minute=20, timezone=KST))
    # 거래량·외인 시장 시그널 배치 (평일 16:35 KST)
    scheduler.add_job(job_refresh_screener_market_signals, CronTrigger(day_of_week="mon-fri", hour=16, minute=35, timezone=KST))
    # DART 공시 카운트 배치 (매일 18:30 KST)
    scheduler.add_job(job_refresh_disclosure_counts, CronTrigger(hour=18, minute=30, timezone=KST))
    # 공시 알림 (평일 16:40 KST)
    scheduler.add_job(job_check_dart_alerts, CronTrigger(day_of_week="mon-fri", hour=16, minute=40, timezone=KST))
    # 거래량 급등 알림 (평일 16:45 KST)
    scheduler.add_job(job_check_volume_alerts, CronTrigger(day_of_week="mon-fri", hour=16, minute=45, timezone=KST))
    # 기술지표 알림 (평일 16:50 KST)
    scheduler.add_job(job_check_technical_alerts, CronTrigger(day_of_week="mon-fri", hour=16, minute=50, timezone=KST))
    scheduler.start()
    logging.getLogger(__name__).info("스케줄러 시작 — 브리핑 15:35 / 알림 5분 / 뉴스 08:50 / 스냅샷 15:32 / 스크리너 16:10·16:20·16:35 / 공시 18:30 / alert고도화 16:40·16:45·16:50")
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(
    title="주식나침반 API",
    description="주식 정보 팩트체크 서비스",
    version="0.1.0",
    lifespan=lifespan,
)

import os as _os

_cors_origins = [o.strip() for o in _os.environ.get("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_api.router, prefix="/api", tags=["auth"])
app.include_router(analyze_api.router, prefix="/api", tags=["analyze"])
app.include_router(realtime_api.router, prefix="/api", tags=["realtime"])
app.include_router(technical_api.router, prefix="/api", tags=["technical"])
app.include_router(upload_api.router, prefix="/api", tags=["upload"])
app.include_router(search_api.router, prefix="/api", tags=["search"])
app.include_router(ask_api.router, prefix="/api", tags=["ask"])
app.include_router(dart_api.router, prefix="/api", tags=["dart"])
app.include_router(factcheck_api.router, prefix="/api", tags=["factcheck"])
app.include_router(portfolio_api.router, prefix="/api", tags=["portfolio"])
app.include_router(market_api.router, prefix="/api", tags=["market"])
app.include_router(watchlist_api.router, prefix="/api", tags=["watchlist"])
app.include_router(notifications_api.router, prefix="/api", tags=["notifications"])
app.include_router(trades_api.router, prefix="/api", tags=["trades"])
app.include_router(profile_api.router, prefix="/api", tags=["profile"])
app.include_router(screener_api.router, prefix="/api", tags=["screener"])
app.include_router(compare_api.router, prefix="/api", tags=["compare"])


@app.get("/")
def root():
    return {
        "service": "주식나침반",
        "version": "0.1.0",
        "status": "alive",
    }


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
