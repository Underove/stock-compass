"""포트폴리오 CRUD + 현재가·차트 + AI 코멘터리."""
import json
import sqlite3
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
def get_chart(stock_code: str, days: int = 90, interval: str | None = None):
    """OHLCV 캔들 차트 데이터 조회.
    - interval 없으면 일봉 (days N 영업일)
    - interval='1m' → KIS 1분봉 30건
    - interval='5m' → KIS 1분봉 2회 호출 후 5분봉 집계 12건
    """
    try:
        if interval in ("5m", "1d"):
            from app.collectors.kis_rest import get_minute_chart_kis
            # 5m: 60분 분량 (12개), 1d: 당일 전체 (390분, 78개)
            span_min = 390 if interval == "1d" else 60
            candles = get_minute_chart_kis(stock_code, interval_min=5, span_min=span_min)
            return {"stock_code": stock_code, "candles": candles, "interval": interval}
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

    COMMENTARY_SYSTEM = """역할: 한국 주식 종목 시황 해설 작성자.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록·주석 금지.

{
  "sentiment": "bullish | bearish | neutral",
  "headline": "현재 상황 한 문장 (수치 1개 포함, 30자~50자)",
  "trend": "최근 30일 흐름 1~2문장 (고저가·기간 수익률 중 1개 인용)",
  "signal": "기술 지표 신호 1문장 (지표명은 괄호로 풀이)",
  "note": "오늘 직접 확인해볼 포인트 1문장"
}

sentiment 판단 기준:
- bullish: 5일선·20일선 정배열 + 등락률 +1% 이상, 또는 RSI 60 이상.
- bearish: 5일선·20일선 역배열 + 등락률 -1% 이하, 또는 RSI 35 이하.
- neutral: 위 둘 모두 아님.

그라운딩 (필수):
- 입력 데이터에 명시된 수치만 사용. 가격·지표 값을 새로 만들거나 추정 금지.
- 데이터 없는 항목은 "확인 불가" 대신 일반 흐름만 서술.

문체:
- 친근체(~이에요/~해요). 형식체(~합니다)·호칭(어르신/여러분/당신)·별표(*) 금지.
- 의인화 금지 ("주가가 힘들어해요" X).
- 단정 대신 관찰체 ("X로 보여요", "X 구간이에요").
- 투자 권유·매수/매도 추천 금지.
- 큰따옴표 안엔 작은따옴표 사용.

예시 출력:
{"sentiment":"bearish","headline":"오늘 1.2% 빠지며 52,400원에 거래되고 있어요.","trend":"최근 30일간 -4.5% 흐름이고 고가 56,800원·저가 51,200원 구간이에요.","signal":"RSI(과매수·과매도 지표)가 38로 저평가 구간에 들어왔어요.","note":"5일선 회복 여부와 거래량 변화를 함께 보시면 좋아요."}"""

    prompt = f"""{corp_name or stock_code} 종목의 아래 시세 및 기술 지표를 바탕으로 JSON 해설을 작성하세요.

[현재 시세]
현재가: {price_data['current_price']:,}원
등락: {price_data['change_pct']:+.2f}% ({price_data['change_amount']:+,}원)
거래량: {price_data['volume']:,}주

[30일 시세 요약]
{chart_summary}{ta_section}"""

    try:
        raw = generate_answer(
            prompt, system_instruction=COMMENTARY_SYSTEM,
            temperature=0.1, max_tokens=400, json_mode=True,
        )
        sections = parse_json_response(raw, default={})
        if not sections or not isinstance(sections.get("headline"), str):
            sections = None
    except Exception:
        raw = "AI 해설을 잠시 후 다시 받아볼 수 있어요."
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

    # 비중 정보 추가 — 리밸런싱 권고용
    weight_lines: list[str] = []
    if stock_pnls and sum(s["current_value"] for s in stock_pnls) > 0:
        total_cv = sum(s["current_value"] for s in stock_pnls)
        sorted_by_w = sorted(stock_pnls, key=lambda s: -s["current_value"])
        for s in sorted_by_w[:5]:
            pct = (s["current_value"] / total_cv) * 100
            weight_lines.append(f"  · {s['corp_name']}: 비중 {pct:.1f}%")

    portfolio_text = "\n".join(lines)
    if weight_lines:
        portfolio_text += "\n\n[종목 비중 (상위 5종목)]\n" + "\n".join(weight_lines)

    BRIEFING_SYSTEM = """역할: 개인 투자자 포트폴리오 일일 브리핑 작성자.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록 금지.

{
  "sentiment": "positive | negative | neutral",
  "summary": "포트폴리오 전반 분위기 1~2문장 (전체 등락 흐름 + 시장 맥락)",
  "highlights": [
    {"corp_name": "종목명", "status": "상승 | 하락 | 보합", "change_note": "금일 +X.X%", "note": "왜 그런지 또는 무엇을 봐야 하는지 한 문장"}
  ],
  "action_items": ["오늘 직접 확인 가능한 행동 1", "행동 2"],
  "watch": "오늘 특별히 주시할 포인트 1문장",
  "risk": "포트폴리오 구성 리스크 1문장"
}

sentiment 판단:
- positive: 보유 종목 중 +1% 이상이 절반 이상.
- negative: 보유 종목 중 -1% 이하가 절반 이상.
- neutral: 위 둘 모두 아님 또는 혼조.

highlights 선정:
- 입력 데이터에 명시된 종목만 사용. 종목명·수치 변경 금지.
- 등락률 절댓값 큰 순으로 1~3개. change_note는 입력의 '금일 X.X%' 값 그대로 인용.

action_items: 2~3개. "X 확인", "Y 점검" 같은 구체적 행위. 투자 권유 금지.

risk 룰 (우선순위 순):
1. 입력 [종목 비중] 섹션에 단일 종목 비중 40% 이상이 있으면 → "OO 비중 X% — 한 종목 집중도가 높아요. 분산 고려해보세요"
2. -10% 이하 종목이 3개 이상이면 → "손실 종목 N개 — 손절 기준이나 평단가 점검이 필요해요"
3. 모두 해당 없으면 → 일반 시장 변동성 한 줄

그라운딩 (필수):
- 입력에 없는 수치·종목 생성 금지. 비중·등락률 추정 금지.
- 시장 상황은 보유 종목 분포에서 보이는 흐름만 언급.

문체:
- 친근체(~이에요/~해요). 형식체·호칭·별표(*) 금지. 의인화 금지.
- 단정 대신 관찰체 ("X해 보여요", "X가 눈에 띄어요").
- 전문 용어는 괄호로 풀이. 큰따옴표 안엔 작은따옴표 사용."""

    prompt = f"""아래 포트폴리오 현황을 바탕으로 오늘의 브리핑 JSON을 작성하세요.

포트폴리오 현황:
{portfolio_text}"""

    try:
        raw = generate_answer(
            prompt, system_instruction=BRIEFING_SYSTEM,
            temperature=0.15, max_tokens=900, json_mode=True,
            model=settings.openai_model_pro,
        )
        sections = parse_json_response(raw, default={})
        if not sections or not isinstance(sections.get("summary"), str):
            sections = None
    except Exception:
        raw = "AI 브리핑을 잠시 후 다시 받아볼 수 있어요."
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


def _compute_insight(snap: dict) -> dict | None:
    """screener_snapshot 행에서 가장 두드러진 시그널 1개 반환.
    tone: positive=빨강(상승신호), negative=파랑(하락신호), neutral=회색(관찰).
    """
    rsi = snap.get("rsi")
    if rsi is not None:
        if rsi < 30:
            return {"text": f"RSI {rsi:.0f} · 과매도 구간", "tone": "positive"}
        if rsi > 70:
            return {"text": f"RSI {rsi:.0f} · 과매수 구간", "tone": "negative"}

    ma = snap.get("ma_status")
    if ma == "golden":
        return {"text": "단기 이평선 골든크로스", "tone": "positive"}
    if ma == "dead":
        return {"text": "단기 이평선 데드크로스", "tone": "negative"}

    vol_ratio = snap.get("volume_ratio")
    if vol_ratio is not None and vol_ratio >= 2.0:
        return {"text": f"거래량 평소의 {vol_ratio:.1f}배", "tone": "neutral"}

    foreign = snap.get("foreign_net_buy")
    if foreign is not None:
        if foreign > 10000:
            return {"text": "외국인 대량 순매수", "tone": "positive"}
        if foreign < -10000:
            return {"text": "외국인 대량 순매도", "tone": "negative"}

    disc = snap.get("disclosure_30d") or 0
    if disc >= 3:
        return {"text": f"최근 공시 활발 (30일 {disc}건)", "tone": "neutral"}

    return None


@router.get("/portfolio/insights")
def get_portfolio_insights(username: str = Depends(get_current_user)):
    """보유 종목별 인라인 한 줄 인사이트. 룰 베이스 (LLM 호출 없음)."""
    from app.db.trade_db import _conn
    items = _load(username)
    codes = [i["stock_code"] for i in items]
    if not codes:
        return {"insights": {}}

    placeholders = ",".join(["?"] * len(codes))
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            f"SELECT * FROM screener_snapshot WHERE stock_code IN ({placeholders})",
            codes,
        ).fetchall()

    insights: dict[str, dict] = {}
    for row in rows:
        snap = dict(row)
        ins = _compute_insight(snap)
        if ins:
            insights[snap["stock_code"]] = ins
    return {"insights": insights}


@router.get("/portfolio/oneliner")
def get_portfolio_oneliner(force: bool = False, username: str = Depends(get_current_user)):
    """대시보드 사이드용 한 줄 AI 브리핑. 1시간 캐시. gpt-5.4 full 사용."""
    import datetime as _dt
    cache_path = _DATA_DIR / f"oneliner_cache_{username}.json"

    if not force and cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached_at = _dt.datetime.fromisoformat(cached.get("_cached_at", ""))
            if _dt.datetime.now() - cached_at < _dt.timedelta(hours=1):
                return {k: v for k, v in cached.items() if not k.startswith("_")}
        except Exception:
            pass

    items = _load(username)
    if not items:
        return {
            "headline": "아직 보유 종목이 없어요",
            "tone": "neutral",
            "generated_at": _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).strftime("%m/%d %H:%M"),
        }

    lines = []
    for item in items[:10]:
        try:
            p = _get_price(item["stock_code"])
            cp = p.get("current_price", 0)
            bp = item.get("buy_price", 0)
            pnl_pct = ((cp - bp) / bp * 100) if bp else 0
            chg_pct = p.get("change_pct", 0)
            lines.append(f"{item['corp_name']}: 현재가 {cp:,}원, 오늘 {chg_pct:+.2f}%, 평가손익 {pnl_pct:+.1f}%")
        except Exception:
            continue

    portfolio_text = "\n".join(lines) if lines else "(시세 조회 불가)"

    SYSTEM = """역할: 포트폴리오 한 줄 헤드라인 작성자.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록 금지.

{"headline": "60자 이내 한 문장", "tone": "positive | negative | neutral"}

규칙:
- headline은 입력에 보이는 가장 두드러진 종목 1~2개 + 등락률 인용.
- 입력에 없는 수치·종목명 생성 금지.
- tone 판단: 합산 평가손익이 +이면 positive, -이면 negative, ±1% 이내면 neutral.

문체:
- 친근체(~이에요/~해요). 형식체·호칭·별표(*) 금지. 의인화 금지.

예시:
{"headline":"SK하이닉스 +5%로 강세, 삼성전자 -1.2% 조정이 눈에 띄어요.","tone":"positive"}"""

    prompt = f"[포트폴리오 현황]\n{portfolio_text}"

    try:
        raw = generate_answer(
            prompt, system_instruction=SYSTEM,
            temperature=0.2, max_tokens=120, json_mode=True,
            model=settings.openai_model_pro,
        )
        parsed = parse_json_response(raw, default={})
        headline = (parsed.get("headline") or "").strip() or "AI 브리핑을 준비 중이에요"
        tone = parsed.get("tone") or "neutral"
        if tone not in ("positive", "negative", "neutral"):
            tone = "neutral"
    except Exception:
        headline = "AI 브리핑을 잠시 후 다시 받아볼 수 있어요"
        tone = "neutral"

    now_kst = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9)))
    result = {
        "headline": headline,
        "tone": tone,
        "generated_at": now_kst.strftime("%m/%d %H:%M"),
        "_cached_at": _dt.datetime.now().isoformat(),
    }
    try:
        cache_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return {k: v for k, v in result.items() if not k.startswith("_")}


@router.get("/portfolio/movers")
def get_portfolio_movers(username: str = Depends(get_current_user)):
    """보유 종목 중 절대등락률 Top 3 + 7일 sparkline."""
    items = _load(username)
    if not items:
        return {"movers": []}

    data = []
    for item in items:
        try:
            p = _get_price(item["stock_code"])
            cp = p.get("current_price", 0)
            chg_pct = p.get("change_pct", 0)
            if not cp or not isinstance(chg_pct, (int, float)):
                continue
            sparkline = []
            try:
                candles = get_chart_data(item["stock_code"], days=10)
                sparkline = [c["close"] for c in candles[-7:]]
            except Exception:
                pass
            data.append({
                "stock_code": item["stock_code"],
                "corp_name": item["corp_name"],
                "current_price": cp,
                "change_pct": chg_pct,
                "sparkline": sparkline,
            })
        except Exception:
            continue

    data.sort(key=lambda x: abs(x["change_pct"]), reverse=True)
    return {"movers": data[:3]}


@router.get("/portfolio/disclosures/{stock_code}")
def get_disclosures(stock_code: str, days: int = 30, with_summary: bool = True):
    """종목코드 기준 최근 DART 공시 목록 조회. with_summary=True면 AI 한 줄 요약 포함 (캐시)."""
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
            "ai_summary": None,
        }
        for d in raw
    ]

    if with_summary and disclosures:
        from app.db.trade_db import get_disclosure_summaries, save_disclosure_summary
        from app.collectors.dart import fetch_disclosure_body
        rcept_nos = [d["rcept_no"] for d in disclosures if d["rcept_no"]]
        cached = get_disclosure_summaries(rcept_nos)

        # 캐시 hit
        for d in disclosures:
            if d["rcept_no"] in cached:
                d["ai_summary"] = cached[d["rcept_no"]]

        # 캐시 miss는 본문 fetch + 배치 LLM
        misses = [d for d in disclosures if d["rcept_no"] and not d["ai_summary"]]
        if misses:
            try:
                bodies = []
                for d in misses[:5]:  # 한 번에 최대 5건만 처리 (API 호출 부담)
                    body = fetch_disclosure_body(d["rcept_no"])
                    if body and len(body) > 200:
                        bodies.append((d["rcept_no"], d["report_nm"], body[:3000]))

                if bodies:
                    SYS = """역할: DART 공시 본문 일괄 요약자.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록 금지.

{"items": [{"rcept_no": "...", "summary": "..."}, ...]}

요약 규칙:
- summary는 한 문장, 최대 50자.
- 본문에 있는 사실·수치만 사용. 수치는 단위 포함(주/원/%). 추정·일반화 금지.
- 핵심 1가지만: '누가 무엇을 얼마나' 구조 (예: '조미선 상무, 보유 120주 늘어 3,409주예요').
- 입력 rcept_no 그대로 매핑. 본문이 비거나 모호하면 해당 항목 제외.

문체:
- 친근체(~이에요/~해요). 형식체·호칭·별표(*) 금지."""

                    prompt_parts = []
                    for rcept_no, report_nm, body in bodies:
                        prompt_parts.append(f"[rcept_no: {rcept_no}]\n[제목: {report_nm}]\n[본문]\n{body}")
                    prompt = "\n\n---\n\n".join(prompt_parts)

                    raw_text = generate_answer(
                        prompt, system_instruction=SYS,
                        temperature=0.1, max_tokens=600, json_mode=True,
                    )
                    parsed_obj = parse_json_response(raw_text, default={})
                    items = parsed_obj.get("items") if isinstance(parsed_obj, dict) else None
                    if not isinstance(items, list):
                        items = []

                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        rno = item.get("rcept_no", "")
                        summ = (item.get("summary") or "").strip()
                        if rno and summ:
                            save_disclosure_summary(rno, summ)
                            for d in disclosures:
                                if d["rcept_no"] == rno:
                                    d["ai_summary"] = summ
                                    break
            except Exception:
                pass  # 요약 실패해도 공시 목록 자체는 반환

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
