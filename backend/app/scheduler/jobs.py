"""24시간 스케줄 잡: 자동 브리핑·알림·뉴스 요약."""
import datetime
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

def _briefing_cache_path(username: str = "") -> Path:
    suffix = f"_{username}" if username else ""
    return DATA_DIR / f"briefing_cache{suffix}.json"
ALERTS_LOG = DATA_DIR / "alerts_log.json"
NEWS_CACHE = DATA_DIR / "premarket_news_cache.json"

KST = datetime.timezone(datetime.timedelta(hours=9))


def _now_kst() -> datetime.datetime:
    return datetime.datetime.now(KST)


# ─── 브리핑 캐시 ─────────────────────────────────────────────────────────────

def load_briefing_cache(username: str = "") -> dict | None:
    """오늘 날짜의 캐시된 브리핑 반환. 없거나 오래됐으면 None."""
    path = _briefing_cache_path(username)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        cached_date = data.get("cached_date", "")
        today = _now_kst().strftime("%Y-%m-%d")
        return data if cached_date == today else None
    except Exception:
        return None


def save_briefing_cache(briefing: dict, username: str = "") -> None:
    data = {**briefing, "cached_date": _now_kst().strftime("%Y-%m-%d")}
    _briefing_cache_path(username).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def job_generate_briefing() -> None:
    """장 마감 후 자동 브리핑 생성 (15:35 KST)."""
    logger.info("[스케줄러] 장 마감 브리핑 자동 생성 시작")
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from app.api.portfolio import get_portfolio_briefing
        result = get_portfolio_briefing()
        save_briefing_cache(result)
        logger.info("[스케줄러] 브리핑 생성 완료")
    except Exception as e:
        logger.error("[스케줄러] 브리핑 생성 실패: %s", e)


# ─── 알림 시스템 ──────────────────────────────────────────────────────────────

def _load_alerts() -> list[dict]:
    if not ALERTS_LOG.exists():
        return []
    try:
        return json.loads(ALERTS_LOG.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_alerts(alerts: list[dict]) -> None:
    ALERTS_LOG.write_text(json.dumps(alerts, ensure_ascii=False, indent=2), encoding="utf-8")


def get_unread_alerts() -> list[dict]:
    return [a for a in _load_alerts() if not a.get("read")]


def mark_alerts_read(alert_ids: list[str]) -> None:
    alerts = _load_alerts()
    for a in alerts:
        if a["id"] in alert_ids:
            a["read"] = True
    _save_alerts(alerts)


def job_check_price_alerts() -> None:
    """목표가·손절가 도달 체크 (장 중 매 5분)."""
    now = _now_kst()
    if now.weekday() >= 5:
        return
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60 or minutes > 15 * 60 + 30:
        return

    logger.info("[스케줄러] 가격 알림 체크")
    try:
        from app.collectors.krx import get_current_price
        items: list[dict] = []
        for f in DATA_DIR.glob("portfolio_*.json"):
            try:
                items.extend(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
        alerts = _load_alerts()
        existing_ids = {a["id"] for a in alerts}
        new_alerts: list[dict] = []

        for item in items:
            if not item.get("target_price") and not item.get("stop_loss"):
                continue
            try:
                price_data = get_current_price(item["stock_code"])
                cp = price_data["current_price"]
                date_str = now.strftime("%Y-%m-%d")

                if item.get("target_price") and cp >= item["target_price"]:
                    alert_id = f"{item['stock_code']}_target_{date_str}"
                    if alert_id not in existing_ids:
                        new_alerts.append({
                            "id": alert_id,
                            "type": "target",
                            "stock_code": item["stock_code"],
                            "corp_name": item["corp_name"],
                            "current_price": cp,
                            "trigger_price": item["target_price"],
                            "message": f"{item['corp_name']} 목표가 {item['target_price']:,}원 도달 (현재 {cp:,}원)",
                            "created_at": now.isoformat(),
                            "read": False,
                        })

                if item.get("stop_loss") and cp <= item["stop_loss"]:
                    alert_id = f"{item['stock_code']}_stoploss_{date_str}"
                    if alert_id not in existing_ids:
                        new_alerts.append({
                            "id": alert_id,
                            "type": "stop_loss",
                            "stock_code": item["stock_code"],
                            "corp_name": item["corp_name"],
                            "current_price": cp,
                            "trigger_price": item["stop_loss"],
                            "message": f"{item['corp_name']} 손절가 {item['stop_loss']:,}원 도달 (현재 {cp:,}원)",
                            "created_at": now.isoformat(),
                            "read": False,
                        })
            except Exception as e:
                logger.warning("[스케줄러] %s 가격 조회 실패: %s", item["stock_code"], e)

        if new_alerts:
            _save_alerts(alerts + new_alerts)
            logger.info("[스케줄러] 신규 알림 %d건 저장", len(new_alerts))
    except Exception as e:
        logger.error("[스케줄러] 알림 체크 실패: %s", e)


# ─── 개장 전 뉴스 요약 ────────────────────────────────────────────────────────

def load_news_cache() -> dict | None:
    if not NEWS_CACHE.exists():
        return None
    try:
        data = json.loads(NEWS_CACHE.read_text(encoding="utf-8"))
        cached_date = data.get("cached_date", "")
        today = _now_kst().strftime("%Y-%m-%d")
        return data if cached_date == today else None
    except Exception:
        return None


def job_premarket_news_summary() -> None:
    """개장 전 뉴스 요약 자동 생성 (08:50 KST)."""
    logger.info("[스케줄러] 개장 전 뉴스 요약 시작")
    try:
        from app.collectors.web_search import search_news
        from app.llm.gemini import generate_answer, parse_json_response

        all_stocks: dict[str, str] = {}
        for f in DATA_DIR.glob("portfolio_*.json"):
            try:
                items = json.loads(f.read_text(encoding="utf-8"))
                for i in items:
                    all_stocks[i["stock_code"]] = i["corp_name"]
            except Exception:
                pass
        for f in DATA_DIR.glob("watchlist_*.json"):
            try:
                items = json.loads(f.read_text(encoding="utf-8"))
                for i in items:
                    all_stocks[i["stock_code"]] = i["corp_name"]
            except Exception:
                pass
        if not all_stocks:
            logger.info("[스케줄러] 종목 없음, 건너뜀")
            return

        all_news: list[str] = []
        for code, name in list(all_stocks.items())[:6]:
            try:
                news = search_news(f"{name} 주식 뉴스", display=3)
                for n in news[:3]:
                    all_news.append(f"[{name}] {n.get('title', '')} — {n.get('description', '')}")
            except Exception:
                pass

        if not all_news:
            logger.info("[스케줄러] 수집된 뉴스 없음")
            return

        news_text = "\n".join(all_news[:15])
        SYSTEM = """당신은 한국 주식 개장 전 뉴스 브리핑 AI입니다.
반드시 아래 JSON 형식으로만 출력하세요.

{
  "date": "날짜 (오늘)",
  "headline": "오늘 장에 가장 영향을 줄 핵심 이슈 한 문장",
  "items": [
    {"corp_name": "종목명", "summary": "핵심 내용 한 문장", "tone": "positive"}
  ],
  "market_outlook": "오늘 장 전반 전망 1~2문장. 투자 권유 금지."
}

규칙:
- items는 실제 뉴스가 있는 종목만, 최대 4개.
- tone은 'positive' / 'negative' / 'neutral' 중 하나.
- 별표(*) 사용 금지."""

        raw = generate_answer(
            f"아래 뉴스를 바탕으로 개장 전 브리핑 JSON을 작성하세요.\n\n{news_text}",
            system_instruction=SYSTEM,
            temperature=0.2,
        )
        sections = parse_json_response(raw, default=None)
        now = _now_kst()
        result = {
            "summary": raw,
            "sections": sections,
            "generated_at": now.strftime("%m/%d %H:%M"),
            "cached_date": now.strftime("%Y-%m-%d"),
        }
        NEWS_CACHE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[스케줄러] 개장 전 뉴스 요약 완료")
    except Exception as e:
        logger.error("[스케줄러] 뉴스 요약 실패: %s", e)


# ─── 포트폴리오 스냅샷 ────────────────────────────────────────────────────────

def job_save_portfolio_snapshots() -> None:
    """장 마감 직후 포트폴리오 스냅샷 저장 (평일 15:32 KST)."""
    logger.info("[스케줄러] 포트폴리오 스냅샷 저장 시작")
    try:
        from app.api.portfolio import _get_price
        from app.db.trade_db import save_snapshot

        now = _now_kst()
        date_str = now.strftime("%Y-%m-%d")

        for f in DATA_DIR.glob("portfolio_*.json"):
            # 파일명에서 username 추출: portfolio_<username>.json
            username = f.stem[len("portfolio_"):]
            try:
                items = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not items:
                continue

            total_value = 0
            total_invested = 0
            for item in items:
                try:
                    p = _get_price(item["stock_code"])
                    cp = p["current_price"]
                    total_value += cp * item["quantity"]
                    total_invested += item["buy_price"] * item["quantity"]
                except Exception:
                    # 시세 조회 실패 시 해당 종목 원금으로 대체
                    total_invested += item["buy_price"] * item["quantity"]
                    total_value += item["buy_price"] * item["quantity"]

            try:
                save_snapshot(username, date_str, total_value, total_invested)
                logger.info("[스케줄러] %s 스냅샷 저장: 평가 %d원", username, total_value)
            except Exception as e:
                logger.warning("[스케줄러] %s 스냅샷 저장 실패: %s", username, e)

        logger.info("[스케줄러] 포트폴리오 스냅샷 저장 완료")
    except Exception as e:
        logger.error("[스케줄러] 스냅샷 저장 실패: %s", e)


def job_refresh_screener_fundamentals() -> None:
    """전 종목 기본적 지표 스냅샷 갱신 (평일 16:10 KST)."""
    logger.info("[스케줄러] 스크리너 기본적 지표 갱신 시작")
    try:
        from app.collectors.screener_collector import fetch_all_fundamentals
        from app.db.trade_db import upsert_screener_snapshot
        rows = fetch_all_fundamentals()
        if rows:
            upsert_screener_snapshot(rows)
            logger.info("[스케줄러] 스크리너 스냅샷 %d종목 저장 완료", len(rows))
        else:
            logger.warning("[스케줄러] 스크리너 수집 결과 없음")
    except Exception as e:
        logger.error("[스케줄러] 스크리너 기본 지표 갱신 실패: %s", e)


def job_refresh_screener_ta() -> None:
    """전 종목 TA 계산 + screener_snapshot 업데이트 (평일 16:20 KST)."""
    logger.info("[스케줄러] 스크리너 TA 배치 계산 시작")
    try:
        from app.collectors.screener_collector import compute_ta_for_top_n
        from app.db.trade_db import upsert_screener_snapshot, query_screener
        ta_rows = compute_ta_for_top_n(3000)
        if ta_rows:
            existing = {r["stock_code"]: r for r in query_screener(limit=5000)}
            merged = []
            for ta in ta_rows:
                base = existing.get(ta["stock_code"])
                if not base:
                    continue
                merged.append({**base, "rsi": ta["rsi"], "ma_status": ta["ma_status"], "has_ta": 1})
            upsert_screener_snapshot(merged)
            logger.info("[스케줄러] TA 배치 완료: %d종목", len(merged))
    except Exception as e:
        logger.error("[스케줄러] TA 배치 실패: %s", e)


def job_refresh_disclosure_counts() -> None:
    """DART 전체 공시 건수 배치 업데이트 (매일 18:30 KST).
    corp_code 없이 bulk 조회 → 종목코드별 30일 공시 카운트 저장."""
    logger.info("[스케줄러] 공시 카운트 배치 시작")
    try:
        from app.collectors.dart import fetch_disclosure_counts_all
        from app.db.trade_db import update_disclosure_counts
        counts = fetch_disclosure_counts_all(days=30)
        if counts:
            update_disclosure_counts(counts)
            logger.info("[스케줄러] 공시 카운트 완료: %d종목", len(counts))
        else:
            logger.warning("[스케줄러] 공시 카운트: 데이터 없음")
    except Exception as e:
        logger.error("[스케줄러] 공시 카운트 실패: %s", e)
