"""포트폴리오 CRUD + 현재가·차트 + AI 코멘터리."""
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.collectors.dart import download_corp_codes, fetch_recent_disclosures
from app.collectors.krx import get_chart_data, get_current_price, search_ticker
from app.collectors.kis_rest import get_current_price_kis, get_fundamental_kis
from app.config import settings
from app.db.trade_db import record_trade


def _get_price(stock_code: str) -> dict:
    """KIS REST 우선, 실패하거나 current_price=0이면 pykrx fallback."""
    if settings.kis_app_key and settings.kis_app_secret:
        try:
            result = get_current_price_kis(stock_code)
            if result.get("current_price", 0) > 0:
                return result
        except Exception:
            pass
    from datetime import datetime, timedelta, timezone
    kst = datetime.now(timezone(timedelta(hours=9)))
    data = get_current_price(stock_code)
    total = kst.hour * 60 + kst.minute
    wd = kst.weekday()
    if wd >= 5:
        session = "closed"
    elif 8 * 60 <= total < 9 * 60:
        session = "pre"
    elif 9 * 60 <= total < 15 * 60 + 30:
        session = "open"
    elif 15 * 60 + 30 <= total < 18 * 60:
        session = "after"
    else:
        session = "closed"
    data["session"] = session
    return data
from app.collectors.ta_engine import analyze as ta_analyze, ta_text_summary
from app.llm.gemini import generate_answer, parse_json_response

router = APIRouter()

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DATA_DIR.mkdir(parents=True, exist_ok=True)


# ─── 스토리지 헬퍼 ───────────────────────────────────────────────────────────

def _portfolio_file(username: str) -> Path:
    return _DATA_DIR / f"portfolio_{username}.json"


def _load(username: str) -> list[dict]:
    f = _portfolio_file(username)
    if not f.exists():
        return []
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def _save(items: list[dict], username: str) -> None:
    with open(_portfolio_file(username), "w", encoding="utf-8") as fp:
        json.dump(items, fp, ensure_ascii=False, indent=2)


# ─── 스키마 ──────────────────────────────────────────────────────────────────

class PortfolioItem(BaseModel):
    stock_code: str
    corp_name: str
    buy_price: int
    quantity: int
    target_price: int | None = None
    stop_loss: int | None = None


class UpdatePortfolioBody(BaseModel):
    buy_price: int
    quantity: int
    target_price: int | None = None
    stop_loss: int | None = None


# ─── 엔드포인트 ──────────────────────────────────────────────────────────────

@router.get("/portfolio")
def list_portfolio(username: str = Depends(get_current_user)):
    return {"items": _load(username)}


@router.post("/portfolio")
def add_portfolio(item: PortfolioItem, username: str = Depends(get_current_user)):
    items = _load(username)
    existing = next((i for i in items if i["stock_code"] == item.stock_code), None)
    if existing:
        existing.update(item.model_dump())
    else:
        items.append(item.model_dump())
    _save(items, username)
    try:
        record_trade(username, item.stock_code, item.corp_name, "buy", item.quantity, item.buy_price)
    except Exception:
        pass
    return {"ok": True, "item": item.model_dump()}


@router.delete("/portfolio/{stock_code}")
def remove_portfolio(stock_code: str, username: str = Depends(get_current_user)):
    items = _load(username)
    target = next((i for i in items if i["stock_code"] == stock_code), None)
    _save([i for i in items if i["stock_code"] != stock_code], username)
    if target:
        try:
            sell_price = _get_price(stock_code).get("current_price") or target["buy_price"]
        except Exception:
            sell_price = target["buy_price"]
        try:
            record_trade(
                username, stock_code, target.get("corp_name", stock_code),
                "sell", target["quantity"], sell_price,
                buy_price=target["buy_price"],
            )
        except Exception:
            pass
    return {"ok": True}


@router.put("/portfolio/{stock_code}")
def update_portfolio(stock_code: str, body: UpdatePortfolioBody, username: str = Depends(get_current_user)):
    items = _load(username)
    target = next((i for i in items if i["stock_code"] == stock_code), None)
    if not target:
        raise HTTPException(status_code=404, detail="종목 없음")

    old_qty = target["quantity"]
    old_buy_price = target["buy_price"]
    corp_name = target.get("corp_name", stock_code)

    if body.quantity <= 0:
        items = [i for i in items if i["stock_code"] != stock_code]
        _save(items, username)
        try:
            sell_price = _get_price(stock_code).get("current_price") or old_buy_price
        except Exception:
            sell_price = old_buy_price
        try:
            record_trade(username, stock_code, corp_name, "sell", old_qty, sell_price, buy_price=old_buy_price)
        except Exception:
            pass
    else:
        qty_diff = old_qty - body.quantity
        price_changed = body.buy_price != old_buy_price
        target["buy_price"] = body.buy_price
        target["quantity"] = body.quantity
        target["target_price"] = body.target_price
        target["stop_loss"] = body.stop_loss
        _save(items, username)
        try:
            sell_price = _get_price(stock_code).get("current_price") or old_buy_price
        except Exception:
            sell_price = old_buy_price
        try:
            if qty_diff > 0:
                record_trade(username, stock_code, corp_name, "sell", qty_diff, sell_price, buy_price=old_buy_price)
            elif qty_diff < 0:
                record_trade(username, stock_code, corp_name, "buy", -qty_diff, body.buy_price)
            elif price_changed:
                record_trade(username, stock_code, corp_name, "edit", body.quantity, body.buy_price, buy_price=old_buy_price)
        except Exception:
            pass
    return {"ok": True}


@router.get("/portfolio/price/{stock_code}")
def get_price(stock_code: str):
    """현재가·등락률 조회 (pykrx)."""
    try:
        data = _get_price(stock_code)
        return data
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/portfolio/chart/{stock_code}")
def get_chart(stock_code: str, days: int = 90):
    """OHLCV 캔들 차트 데이터 조회."""
    try:
        candles = get_chart_data(stock_code, days=days)
        return {"stock_code": stock_code, "candles": candles}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/portfolio/search")
def search_stock(q: str):
    """종목명 검색 (DART 코드 + 종목코드)."""
    results = search_ticker(q)
    return {"results": results}


@router.get("/portfolio/commentary/{stock_code}")
def get_commentary(stock_code: str, corp_name: str = ""):
    """최근 시세 + DART 공시 기반 AI 코멘터리 생성."""
    try:
        price_data = _get_price(stock_code)
        candles = get_chart_data(stock_code, days=30)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"시세 조회 실패: {e}")

    # 최근 30일 요약
    if candles:
        prices = [c["close"] for c in candles]
        first_price = prices[0]
        last_price = prices[-1]
        pct_30d = round((last_price - first_price) / first_price * 100, 1) if first_price else 0
        high_30d = max(c["high"] for c in candles)
        low_30d = min(c["low"] for c in candles)
        chart_summary = (
            f"최근 30일 최고가: {high_30d:,}원, 최저가: {low_30d:,}원, "
            f"기간 수익률: {pct_30d:+.1f}%"
        )
    else:
        chart_summary = "차트 데이터 없음"

    # 기술적 지표 (실패해도 폴백)
    try:
        ta = ta_analyze(stock_code)
        ta_section = f"\n\n[기술적 지표]\n{ta_text_summary(ta)}"
    except Exception:
        ta_section = ""

    COMMENTARY_SYSTEM = """당신은 한국 상장 주식 AI 해설 시스템입니다.
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 절대 출력하지 마세요.

{
  "sentiment": "bullish",
  "headline": "현재 상황을 한 문장으로 요약. 수치 1개 포함. 예: '오늘 1.2% 하락하며 52,400원에 거래 중입니다.'",
  "trend": "최근 흐름과 배경 1~2문장. 30일 고저가·기간 수익률 등 구체적 수치 포함.",
  "signal": "기술적 지표 신호 1문장. 전문 용어는 반드시 괄호로 풀어 쓰기. 예: 'RSI(과매수·과매도 지표)가 38로 저평가 구간에 접근 중입니다.'",
  "note": "투자자가 오늘 확인해볼 포인트 1문장. 투자 권유 금지."
}

추가 규칙:
- sentiment는 기술지표·가격 흐름 종합: "bullish" / "bearish" / "neutral" 중 하나.
- 별표(*) 사용 금지. 큰따옴표 안 텍스트에는 작은따옴표 사용.
- 라디오 진행자처럼 친근하고 차분하게."""

    prompt = f"""{corp_name or stock_code} 종목의 아래 시세 및 기술 지표를 바탕으로 JSON 해설을 작성하세요.

[현재 시세]
현재가: {price_data['current_price']:,}원
등락: {price_data['change_pct']:+.2f}% ({price_data['change_amount']:+,}원)
거래량: {price_data['volume']:,}주

[30일 시세 요약]
{chart_summary}{ta_section}"""

    try:
        raw = generate_answer(prompt, system_instruction=COMMENTARY_SYSTEM, temperature=0.2)
        sections = parse_json_response(raw, default=None)
        if not sections or not isinstance(sections.get("headline"), str):
            sections = None
    except Exception:
        raw = "AI 해설을 일시적으로 불러오지 못했습니다."
        sections = None

    return {
        "stock_code": stock_code,
        "corp_name": corp_name,
        "price": price_data,
        "commentary": raw,
        "commentary_sections": sections,
    }


@router.get("/portfolio/briefing")
def get_portfolio_briefing(force: bool = False, username: str = Depends(get_current_user)):
    """포트폴리오 전체 기반 AI 오늘의 브리핑. force=true면 캐시 무시."""
    import datetime

    if not force:
        from app.scheduler.jobs import load_briefing_cache
        cached = load_briefing_cache(username)
        if cached:
            return cached

    items = _load(username)
    if not items:
        return {
            "briefing": "포트폴리오에 종목이 없습니다. 종목을 추가하면 AI 브리핑을 받을 수 있어요.",
            "sections": None, "generated_at": "", "portfolio_stats": None,
        }

    lines: list[str] = []
    stock_pnls: list[dict] = []

    for item in items[:8]:
        try:
            price = _get_price(item["stock_code"])
            cp = price["current_price"]
            day_pct = price.get("change_pct", 0)
            pnl_pct = ((cp - item["buy_price"]) / item["buy_price"] * 100) if item["buy_price"] else 0
            pnl_amt = (cp - item["buy_price"]) * item["quantity"]
            invested = item["buy_price"] * item["quantity"]
            lines.append(
                f"- {item['corp_name']}: 현재 {cp:,}원 "
                f"(금일 {day_pct:+.1f}% / 평가손익 {pnl_pct:+.1f}%, {pnl_amt:+,.0f}원)"
            )
            stock_pnls.append({
                "corp_name": item["corp_name"],
                "pnl_pct": round(pnl_pct, 2),
                "invested": invested,
                "current_value": cp * item["quantity"],
            })
        except Exception:
            lines.append(f"- {item['corp_name']}: 시세 조회 불가")

    # 포트폴리오 통계 계산
    portfolio_stats = None
    if stock_pnls:
        total_invested = sum(s["invested"] for s in stock_pnls)
        total_current = sum(s["current_value"] for s in stock_pnls)
        total_pnl_pct = ((total_current - total_invested) / total_invested * 100) if total_invested else 0
        sorted_by_pnl = sorted(stock_pnls, key=lambda s: s["pnl_pct"])
        portfolio_stats = {
            "total_pnl_pct": round(total_pnl_pct, 2),
            "stock_count": len(stock_pnls),
            "best": {"corp_name": sorted_by_pnl[-1]["corp_name"], "pnl_pct": sorted_by_pnl[-1]["pnl_pct"]},
            "worst": {"corp_name": sorted_by_pnl[0]["corp_name"], "pnl_pct": sorted_by_pnl[0]["pnl_pct"]},
        }

    portfolio_text = "\n".join(lines)

    BRIEFING_SYSTEM = """당신은 한국 주식 포트폴리오 AI 브리핑 시스템입니다.
반드시 아래 JSON 형식으로만 출력하세요. 다른 텍스트는 절대 출력하지 마세요.

{
  "sentiment": "positive",
  "summary": "오늘 포트폴리오 전반 분위기 1~2문장. 전체 흐름과 시장 상황 중심.",
  "highlights": [
    {"corp_name": "종목명", "status": "상승", "change_note": "금일 +2.1%", "note": "이 종목 핵심 포인트 한 문장"}
  ],
  "action_items": ["오늘 구체적으로 확인할 항목 1", "항목 2"],
  "watch": "오늘 특히 주의해서 볼 포인트 1문장",
  "risk": "포트폴리오 리스크 또는 유의사항 1문장"
}

규칙:
- sentiment는 포트폴리오 전반 분위기: "positive" / "negative" / "neutral" 중 하나만.
- highlights는 가장 주목할 1~3개 종목만. change_note는 "금일 +X.X%" 형식으로 간결하게.
- status 값은 반드시 '상승', '하락', '보합' 중 하나.
- action_items는 오늘 투자자가 직접 확인해볼 수 있는 2~3가지 구체적 체크리스트. 투자 권유 금지.
- risk는 분산 부족, 특정 섹터 쏠림, 손실 위험 등 실질적 유의사항.
- 투자 권유·매수·매도 추천 절대 금지.
- 별표(*) 사용 금지. 큰따옴표 안 텍스트에는 작은따옴표 사용.
- 전문 용어는 괄호로 쉽게 풀어 설명."""

    prompt = f"""아래 포트폴리오 현황을 바탕으로 오늘의 브리핑 JSON을 작성하세요.

포트폴리오 현황:
{portfolio_text}"""

    try:
        raw = generate_answer(prompt, system_instruction=BRIEFING_SYSTEM, temperature=0.25, model=settings.openai_model_pro)
        sections = parse_json_response(raw, default=None)
        if not sections or not isinstance(sections.get("summary"), str):
            sections = None
    except Exception:
        raw = "AI 브리핑 생성에 실패했습니다. 잠시 후 다시 시도해주세요."
        sections = None

    result = {
        "briefing": raw,
        "sections": sections,
        "generated_at": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime("%m/%d %H:%M"),
        "portfolio_stats": portfolio_stats,
    }
    try:
        from app.scheduler.jobs import save_briefing_cache
        save_briefing_cache(result, username)
    except Exception:
        pass
    return result


@router.get("/portfolio/disclosures/{stock_code}")
def get_disclosures(stock_code: str, days: int = 30):
    """종목코드 기준 최근 DART 공시 목록 조회."""
    try:
        companies = download_corp_codes()
    except Exception:
        return {"stock_code": stock_code, "disclosures": []}

    company = next((c for c in companies if c["stock_code"] == stock_code), None)
    if not company:
        return {"stock_code": stock_code, "disclosures": []}

    try:
        raw = fetch_recent_disclosures(company["corp_code"], days=days, max_count=10)
    except Exception:
        return {"stock_code": stock_code, "disclosures": []}

    disclosures = [
        {
            "report_nm": d.get("report_nm", ""),
            "rcept_dt": d.get("rcept_dt", ""),
            "flr_nm": d.get("flr_nm", ""),
            "rcept_no": d.get("rcept_no", ""),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d.get('rcept_no', '')}",
        }
        for d in raw
    ]
    return {"stock_code": stock_code, "disclosures": disclosures}


@router.get("/portfolio/fundamental/{stock_code}")
def get_fundamental(stock_code: str):
    """재무 지표 (PER/PBR/EPS/BPS/시가총액) — KIS 우선, pykrx 폴백."""
    empty = {"per": None, "pbr": None, "eps": None, "div": None, "bps": None, "market_cap": None}

    # KIS 우선
    if settings.kis_app_key and settings.kis_app_secret:
        try:
            result = get_fundamental_kis(stock_code)
            if any(v is not None for v in result.values()):
                return result
        except Exception:
            pass

    # pykrx 폴백
    import datetime
    from pykrx import stock as pykrx_stock

    _kst = datetime.timezone(datetime.timedelta(hours=9))
    _today = datetime.datetime.now(_kst).date()
    today = _today.strftime("%Y%m%d")
    start = (_today - datetime.timedelta(days=14)).strftime("%Y%m%d")

    try:
        df_fund = pykrx_stock.get_market_fundamental_by_date(start, today, stock_code)
        if df_fund is None or df_fund.empty:
            return empty
        r = df_fund.iloc[-1]

        def pos(val):
            v = float(val) if val is not None else 0
            return v if v > 0 else None

        df_cap = pykrx_stock.get_market_cap_by_date(start, today, stock_code)
        market_cap = None
        if df_cap is not None and not df_cap.empty:
            cap_val = df_cap.iloc[-1].get("시가총액", 0)
            market_cap = int(cap_val) if cap_val else None

        return {
            "per": pos(r.get("PER")), "pbr": pos(r.get("PBR")),
            "eps": float(r.get("EPS", 0)) or None,
            "div": pos(r.get("DIV")), "bps": pos(r.get("BPS")),
            "market_cap": market_cap,
        }
    except Exception:
        return empty


@router.get("/portfolio/trading-flow/{stock_code}")
def get_trading_flow(stock_code: str, days: int = 5):
    """외국인·기관 순매수 흐름 (최근 N 거래일) — pykrx."""
    import datetime
    from pykrx import stock as pykrx_stock

    _kst = datetime.timezone(datetime.timedelta(hours=9))
    _today = datetime.datetime.now(_kst).date()
    today = _today.strftime("%Y%m%d")
    start = (_today - datetime.timedelta(days=days * 3)).strftime("%Y%m%d")

    try:
        df = pykrx_stock.get_market_trading_value_by_date(start, today, stock_code, detail=True)
        if df is None or df.empty:
            return {"flow": []}
        df = df.tail(days)
        result = []
        for date, row in df.iterrows():
            foreign_net = int(row.get("외국인합계", row.get("외국인", 0)))
            institution_net = int(row.get("기관합계", row.get("기관", 0)))
            date_str = date.strftime("%m/%d") if hasattr(date, "strftime") else str(date)[5:10]
            result.append({"date": date_str, "foreign_net": foreign_net, "institution_net": institution_net})
        return {"flow": result}
    except Exception:
        return {"flow": []}


@router.get("/portfolio/news/{stock_code}")
def get_stock_news(stock_code: str, corp_name: str = ""):
    """종목 관련 뉴스 — 네이버 검색 API."""
    from app.collectors.web_search import search_news

    items = search_news(f"{corp_name or stock_code} 주식", display=5)
    return {"news": items}


@router.get("/portfolio/short-selling/{stock_code}")
def get_short_selling(stock_code: str, days: int = 5):
    """공매도 비율 추이 — pykrx."""
    import datetime
    from pykrx import stock as pykrx_stock

    _kst = datetime.timezone(datetime.timedelta(hours=9))
    _today = datetime.datetime.now(_kst).date()
    today = _today.strftime("%Y%m%d")
    start = (_today - datetime.timedelta(days=days * 3)).strftime("%Y%m%d")
    try:
        df = pykrx_stock.get_stock_short_selling_volume_by_date(start, today, stock_code)
        if df is None or df.empty:
            return {"ratio": None, "trend": []}
        df = df.tail(days)
        trend = []
        for date, row in df.iterrows():
            trend.append({
                "date": date.strftime("%m/%d") if hasattr(date, "strftime") else str(date)[5:10],
                "ratio": float(row.get("비중", 0)),
            })
        latest = trend[-1]["ratio"] if trend else None
        return {"ratio": latest, "trend": trend}
    except Exception:
        return {"ratio": None, "trend": []}


def _notes_file(username: str) -> Path:
    return _DATA_DIR / f"notes_{username}.json"


def _load_notes(username: str) -> dict:
    f = _notes_file(username)
    if not f.exists():
        return {}
    with open(f, encoding="utf-8") as fp:
        return json.load(fp)


def _save_notes(notes: dict, username: str) -> None:
    with open(_notes_file(username), "w", encoding="utf-8") as fp:
        json.dump(notes, fp, ensure_ascii=False, indent=2)


class NoteBody(BaseModel):
    note: str = ""


@router.get("/portfolio/notes/{stock_code}")
def get_note(stock_code: str, username: str = Depends(get_current_user)):
    return {"note": _load_notes(username).get(stock_code, "")}


@router.put("/portfolio/notes/{stock_code}")
def save_note(stock_code: str, body: NoteBody, username: str = Depends(get_current_user)):
    notes = _load_notes(username)
    notes[stock_code] = body.note
    _save_notes(notes, username)
    return {"ok": True}


@router.get("/portfolio/alerts")
def get_portfolio_alerts(username: str = Depends(get_current_user)):
    """포트폴리오 종목별 미읽은 알림 건수 (배지용)."""
    items = _load(username)
    if not items:
        return {"alerts": {}}
    stock_codes = [item["stock_code"] for item in items]
    from app.db.trade_db import get_unread_alert_counts
    counts = get_unread_alert_counts(username, stock_codes)
    return {"alerts": {code: counts.get(code, 0) for code in stock_codes}}
