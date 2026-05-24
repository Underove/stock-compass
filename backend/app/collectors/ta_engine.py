"""pandas 기반 기술적 지표 계산 엔진 (TA-Lib 없이 순수 pandas 구현)."""
import math

import pandas as pd

from app.collectors.krx import get_chart_data


def _safe(val, digits: int = 0):
    """NaN / inf → None, 나머지는 반올림 후 반환."""
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, digits) if digits else int(round(f))


def _cross_status(fast: pd.Series, slow: pd.Series) -> str:
    """
    two MA series → 교차 상태 문자열
    golden | dead | above | below | none
    """
    valid_f = fast.dropna()
    valid_s = slow.dropna()
    if len(valid_f) < 2 or len(valid_s) < 2:
        return "none"
    f_cur, f_prv = float(fast.iloc[-1]), float(fast.iloc[-2])
    s_cur, s_prv = float(slow.iloc[-1]), float(slow.iloc[-2])
    if any(math.isnan(x) for x in (f_cur, f_prv, s_cur, s_prv)):
        return "none"
    if f_prv <= s_prv and f_cur > s_cur:
        return "golden"
    if f_prv >= s_prv and f_cur < s_cur:
        return "dead"
    return "above" if f_cur > s_cur else "below"


def analyze(stock_code: str) -> dict:
    """종목코드 → 기술적 지표 dict 반환. 데이터 부족 시 error 키 포함."""
    candles = get_chart_data(stock_code, days=252)
    if len(candles) < 20:
        return {"error": "데이터 부족 (최소 20거래일 필요)"}

    df = pd.DataFrame(candles)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["close"]).reset_index(drop=True)

    close = df["close"]
    current = float(close.iloc[-1])

    # ── 이동평균 ────────────────────────────────────────────────────────────────
    ma5  = close.rolling(5).mean()
    ma20 = close.rolling(20).mean()
    ma60 = close.rolling(60).mean()

    cross_5_20  = _cross_status(ma5, ma20)
    cross_20_60 = _cross_status(ma20, ma60)

    # ── RSI (14) ────────────────────────────────────────────────────────────────
    delta = close.diff()
    gain  = delta.clip(lower=0).rolling(14).mean()
    loss  = (-delta.clip(upper=0)).rolling(14).mean()
    rs    = gain / loss.replace(0, float("nan"))
    rsi   = 100 - 100 / (1 + rs)

    # ── MACD (12, 26, 9) ────────────────────────────────────────────────────────
    ema12       = close.ewm(span=12, adjust=False).mean()
    ema26       = close.ewm(span=26, adjust=False).mean()
    macd_line   = ema12 - ema26
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram   = macd_line - signal_line

    # ── 볼린저밴드 (20, ±2σ) ────────────────────────────────────────────────────
    bb_mid   = close.rolling(20).mean()
    bb_std   = close.rolling(20).std(ddof=1)
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std

    bb_upper_v = _safe(bb_upper.iloc[-1])
    bb_lower_v = _safe(bb_lower.iloc[-1])
    bb_pos = None
    if bb_upper_v and bb_lower_v and bb_upper_v > bb_lower_v:
        bb_pos = round((current - bb_lower_v) / (bb_upper_v - bb_lower_v) * 100, 1)
        bb_pos = max(0.0, min(100.0, bb_pos))

    # ── 지지선 / 저항선 (최근 60거래일 로컬 극값) ─────────────────────────────
    recent = df.tail(60).reset_index(drop=True)
    local_highs: list[float] = []
    local_lows:  list[float] = []
    for i in range(1, len(recent) - 1):
        h = recent["high"]
        lo = recent["low"]
        if h.iloc[i] >= h.iloc[i - 1] and h.iloc[i] >= h.iloc[i + 1]:
            local_highs.append(float(h.iloc[i]))
        if lo.iloc[i] <= lo.iloc[i - 1] and lo.iloc[i] <= lo.iloc[i + 1]:
            local_lows.append(float(lo.iloc[i]))

    resistances = sorted(x for x in local_highs if x > current)
    supports    = sorted((x for x in local_lows  if x < current), reverse=True)

    # ── 52주 고저 ───────────────────────────────────────────────────────────────
    high_52w = float(df["high"].max())
    low_52w  = float(df["low"].min())
    pos_52w  = (
        round((current - low_52w) / (high_52w - low_52w) * 100, 1)
        if high_52w > low_52w else 50.0
    )

    return {
        "current_price": current,
        # 이동평균
        "ma5":          _safe(ma5.iloc[-1]),
        "ma20":         _safe(ma20.iloc[-1]),
        "ma60":         _safe(ma60.iloc[-1]),
        "cross_5_20":   cross_5_20,
        "cross_20_60":  cross_20_60,
        # RSI
        "rsi":          _safe(rsi.iloc[-1], 1),
        # MACD
        "macd":         _safe(macd_line.iloc[-1],   2),
        "macd_signal":  _safe(signal_line.iloc[-1], 2),
        "macd_histogram": _safe(histogram.iloc[-1], 2),
        # 볼린저밴드
        "bb_upper":     _safe(bb_upper.iloc[-1]),
        "bb_mid":       _safe(bb_mid.iloc[-1]),
        "bb_lower":     _safe(bb_lower.iloc[-1]),
        "bb_position":  bb_pos,        # 0(하단)~100(상단)
        # 지지 / 저항
        "support":      int(supports[0])    if supports    else None,
        "resistance":   int(resistances[0]) if resistances else None,
        # 52주
        "high_52w":     int(high_52w),
        "low_52w":      int(low_52w),
        "pos_in_52w_range": pos_52w,
    }


def ta_text_summary(ta: dict) -> str:
    """TA dict → LLM 프롬프트용 텍스트 요약."""
    if ta.get("error"):
        return f"기술적 지표 계산 실패: {ta['error']}"

    cross_label = {
        "golden": "골든크로스 발생(매수 신호)",
        "dead":   "데드크로스 발생(매도 신호)",
        "above":  "MA5 > MA20 (단기 상승 추세)",
        "below":  "MA5 < MA20 (단기 하락 추세)",
        "none":   "",
    }

    lines = []

    ma_parts = []
    for key, label in (("ma5", "MA5"), ("ma20", "MA20"), ("ma60", "MA60")):
        v = ta.get(key)
        if v:
            rel = "상회" if ta["current_price"] > v else "하회"
            ma_parts.append(f"{label} {v:,}원({rel})")
    if ma_parts:
        c = cross_label.get(ta.get("cross_5_20", "none"), "")
        lines.append("이동평균: " + ", ".join(ma_parts) + (f" — {c}" if c else ""))

    rsi = ta.get("rsi")
    if rsi is not None:
        zone = "과매도" if rsi < 30 else "과매수" if rsi > 70 else "중립"
        lines.append(f"RSI(14): {rsi} ({zone} 구간)")

    hist = ta.get("macd_histogram")
    if hist is not None:
        sig = "매수" if hist > 0 else "매도"
        lines.append(f"MACD: {ta.get('macd', 0):+.1f}, 시그널 대비 {sig} 신호 (히스토그램 {hist:+.1f})")

    bb_u, bb_m, bb_l = ta.get("bb_upper"), ta.get("bb_mid"), ta.get("bb_lower")
    if bb_u and bb_m and bb_l:
        pos = ta.get("bb_position")
        pos_txt = f"밴드 내 {pos}% 위치" if pos is not None else ""
        lines.append(f"볼린저밴드: 상단 {bb_u:,} / 중간 {bb_m:,} / 하단 {bb_l:,}원 {pos_txt}")

    sup, res = ta.get("support"), ta.get("resistance")
    if sup or res:
        lines.append(f"지지선: {sup:,}원, 저항선: {res:,}원" if sup and res
                     else f"지지선: {sup:,}원" if sup else f"저항선: {res:,}원")

    h52, l52, pos52 = ta.get("high_52w"), ta.get("low_52w"), ta.get("pos_in_52w_range")
    if h52 and l52:
        lines.append(f"52주 범위: {l52:,}~{h52:,}원 (현재 {pos52}% 위치)")

    return "\n".join(lines)
