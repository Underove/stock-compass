from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.db.trade_db import delete_trade, get_realized_summary, get_snapshots, get_trades, update_memo, update_trade

router = APIRouter()


class TradeOut(BaseModel):
    id: int
    stock_code: str
    corp_name: str
    trade_type: str
    quantity: int
    price: int
    buy_price: int | None
    memo: str | None
    created_at: str


class TradesResponse(BaseModel):
    trades: list[TradeOut]
    total: int


class MemoRequest(BaseModel):
    memo: str = Field(..., max_length=500)


class TradeSummaryItem(BaseModel):
    trade_id: int
    date: str
    corp_name: str
    stock_code: str
    quantity: int
    sell_price: int
    buy_price: int
    realized_pnl: int


class SnapshotOut(BaseModel):
    snapshot_date: str
    total_value: int
    total_invested: int


@router.get("/trades", response_model=TradesResponse)
def list_trades(
    limit: int = 50,
    offset: int = 0,
    stock_code: str | None = None,
    username: str = Depends(get_current_user),
) -> TradesResponse:
    trades, total = get_trades(username, limit=limit, offset=offset, stock_code=stock_code)
    return TradesResponse(trades=[TradeOut(**t) for t in trades], total=total)


@router.post("/trades/{trade_id}/memo")
def set_memo(
    trade_id: int,
    body: MemoRequest,
    username: str = Depends(get_current_user),
) -> dict:
    ok = update_memo(username, trade_id, body.memo)
    if not ok:
        raise HTTPException(404, "거래 내역을 찾을 수 없습니다")
    return {"ok": True}


@router.get("/trades/summary")
def trades_summary(username: str = Depends(get_current_user)) -> dict:
    rows = get_realized_summary(username)
    items = [
        TradeSummaryItem(
            trade_id=r["id"],
            date=r["date"],
            corp_name=r["corp_name"],
            stock_code=r["stock_code"],
            quantity=r["quantity"],
            sell_price=r["price"],
            buy_price=r["buy_price"],
            realized_pnl=r["realized_pnl"],
        )
        for r in rows
    ]
    return {"items": [i.model_dump() for i in items]}


class TradeUpdateRequest(BaseModel):
    trade_type: str = Field(..., pattern="^(buy|sell|edit)$")
    quantity: int = Field(..., ge=1)
    price: int = Field(..., ge=0)
    buy_price: int | None = None


@router.put("/trades/{trade_id}")
def edit_trade(
    trade_id: int,
    body: TradeUpdateRequest,
    username: str = Depends(get_current_user),
) -> dict:
    ok = update_trade(username, trade_id, body.trade_type, body.quantity, body.price, body.buy_price)
    if not ok:
        raise HTTPException(404, "거래 내역을 찾을 수 없습니다")
    return {"ok": True}


@router.delete("/trades/{trade_id}")
def remove_trade(
    trade_id: int,
    username: str = Depends(get_current_user),
) -> dict:
    ok = delete_trade(username, trade_id)
    if not ok:
        raise HTTPException(404, "거래 내역을 찾을 수 없습니다")
    return {"ok": True}


@router.get("/portfolio/snapshots")
def portfolio_snapshots(
    days: int = 90,
    username: str = Depends(get_current_user),
) -> dict:
    snaps = get_snapshots(username, days=days)
    return {"snapshots": [SnapshotOut(**s).model_dump() for s in snaps]}


# ─── AI 매매 패턴 진단 ───────────────────────────────────────────────────────────

from pathlib import Path as _Path
import datetime as _dt
import json as _json
from app.config import settings as _settings
from app.llm.gemini import generate_answer as _generate_answer, parse_json_response as _parse_json

_DATA_DIR = _Path(__file__).resolve().parent.parent.parent / "data"


@router.get("/trades/diagnose")
def diagnose_trading_pattern(force: bool = False, username: str = Depends(get_current_user)) -> dict:
    """매매일지를 분석해 행동 패턴 진단. 1주일 캐시."""
    cache_path = _DATA_DIR / f"trade_diagnose_{username}.json"

    if not force and cache_path.exists():
        try:
            cached = _json.loads(cache_path.read_text(encoding="utf-8"))
            cached_at = _dt.datetime.fromisoformat(cached.get("_cached_at", ""))
            if _dt.datetime.now() - cached_at < _dt.timedelta(days=7):
                return {k: v for k, v in cached.items() if not k.startswith("_")}
        except Exception:
            pass

    trades, total = get_trades(username, limit=200)
    if total < 5:
        return {
            "diagnosis": "매매 기록이 5건 미만이라 패턴 분석이 어려워요. 매매를 더 쌓아보세요.",
            "patterns": [],
            "trade_count": total,
            "generated_at": _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9))).strftime("%Y-%m-%d"),
        }

    # 매매 데이터 텍스트화
    realized = get_realized_summary(username)
    lines = []
    for t in trades[:50]:  # 최근 50건
        amount = t["price"] * t["quantity"]
        pnl_text = ""
        if t["trade_type"] == "sell" and t.get("buy_price"):
            pnl = (t["price"] - t["buy_price"]) * t["quantity"]
            pnl_pct = ((t["price"] - t["buy_price"]) / t["buy_price"] * 100) if t["buy_price"] else 0
            pnl_text = f" / 실현 {pnl:+,}원 ({pnl_pct:+.1f}%)"
        lines.append(f"{t['created_at'][:10]} {t['corp_name']} {t['trade_type']} {t['quantity']}주 × {t['price']:,}원 = {amount:,}원{pnl_text}")

    trade_text = "\n".join(lines)
    total_realized = sum(s["realized_pnl"] for s in realized)
    winning = [s for s in realized if s["realized_pnl"] > 0]
    losing = [s for s in realized if s["realized_pnl"] < 0]

    summary_stats = (
        f"총 매매 건수: {total}건\n"
        f"실현된 종목 수: {len(realized)}개\n"
        f"수익 종목: {len(winning)}개 / 손실 종목: {len(losing)}개\n"
        f"누적 실현손익: {total_realized:+,}원"
    )

    SYSTEM = """역할: 개인 투자자 매매 행동 분석가.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록 금지.

{
  "diagnosis": "전체 흐름 1~2문장 (수치 1개 이상 인용)",
  "patterns": [
    {"label": "8자 이내 패턴 이름", "detail": "구체 관찰 1문장 (수치 포함)", "tone": "positive | negative | neutral"}
  ]
}

분석 관점 (입력 데이터에서 보이는 것만):
- 매수/매도 비율, 같은 종목 반복 매매 빈도
- 수익 실현 비율 (수익 종목 수 / 실현 종목 수)
- 손실 폭 평균 vs 수익 폭 평균
- 매매 사이즈 일관성 (한 거래당 금액 편차)
- 보유 종목 다양성 (집중 vs 분산)

tone 기준:
- positive: 좋은 습관 (예: 손절 일관성, 분산 매매)
- negative: 개선 여지 (예: 추격 매수, 손실 종목 추가 매수)
- neutral: 관찰 사실 (좋고 나쁨 불명확)

patterns: 3~5개. 가장 두드러진 것 위주.

그라운딩 (필수):
- 입력 누적 통계·매매 내역에 있는 수치만 인용. 추정·일반화 금지.
- "고점 매수 경향"처럼 외부 시세 비교가 필요한 판단은 데이터에 명백히 보일 때만.

문체:
- 친근체(~이에요/~해요). 형식체·호칭(어르신/여러분/당신)·별표(*) 금지.
- 단정 대신 관찰체 ("X 비율이 Y%로 보여요", "X 경향이 있어요").
- 투자 권유·매수/매도 추천 금지."""

    prompt = f"[누적 통계]\n{summary_stats}\n\n[최근 매매 (최대 50건)]\n{trade_text}"

    try:
        raw = _generate_answer(
            prompt, system_instruction=SYSTEM,
            temperature=0.15, max_tokens=800, json_mode=True,
            model=_settings.openai_model_pro,
        )
        parsed = _parse_json(raw, default={})
        diagnosis = (parsed.get("diagnosis") or "").strip() or "매매 패턴 분석을 잠시 후 다시 받아볼 수 있어요."
        patterns_raw = parsed.get("patterns") or []
        patterns = []
        for p in patterns_raw:
            if not isinstance(p, dict):
                continue
            tone = p.get("tone") or "neutral"
            if tone not in ("positive", "negative", "neutral"):
                tone = "neutral"
            patterns.append({
                "label": (p.get("label") or "").strip(),
                "detail": (p.get("detail") or "").strip(),
                "tone": tone,
            })
    except Exception:
        diagnosis = "AI 진단을 잠시 후 다시 받아볼 수 있어요."
        patterns = []

    now_kst = _dt.datetime.now(_dt.timezone(_dt.timedelta(hours=9)))
    result = {
        "diagnosis": diagnosis,
        "patterns": patterns,
        "trade_count": total,
        "generated_at": now_kst.strftime("%Y-%m-%d"),
        "_cached_at": _dt.datetime.now().isoformat(),
    }
    try:
        cache_path.write_text(_json.dumps(result, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass
    return {k: v for k, v in result.items() if not k.startswith("_")}
