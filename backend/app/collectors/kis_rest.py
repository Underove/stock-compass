"""KIS REST API — 현재가 + 재무지표 조회 (실전/모의 공용, pykrx 대체)."""
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.collectors.kis_ws import get_access_token
from app.config import settings

_NAVER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept-Language": "ko-KR,ko",
}


def get_dividend_yield_naver(stock_code: str) -> float | None:
    """네이버 금융에서 배당수익률(%) 스크래핑. 실패 시 None."""
    try:
        r = httpx.get(
            "https://finance.naver.com/item/main.nhn",
            params={"code": stock_code},
            headers=_NAVER_HEADERS,
            follow_redirects=True,
            timeout=8,
        )
        m = re.search(r'id="_dvr">([\d.]+)<', r.text)
        if m:
            val = float(m.group(1))
            return val if val > 0 else None
    except Exception:
        pass
    return None

_KST = timezone(timedelta(hours=9))

_REST_BASE = (
    "https://openapivts.koreainvestment.com:29443"
    if settings.kis_is_mock
    else "https://openapi.koreainvestment.com:9443"
)


def _session_from_kst(kst: datetime) -> str:
    if kst.weekday() >= 5:
        return "closed"
    total = kst.hour * 60 + kst.minute
    if 8 * 60 <= total < 9 * 60:
        return "pre"
    if 9 * 60 <= total < 15 * 60 + 30:
        return "open"
    if 15 * 60 + 30 <= total < 18 * 60:
        return "after"
    return "closed"


def _inquire_price(stock_code: str, market_code: str = "J") -> dict:
    """FHKST01010100 호출 → output dict 반환. market_code: J=KOSPI, Q=KOSDAQ"""
    token = get_access_token()
    r = httpx.get(
        f"{_REST_BASE}/uapi/domestic-stock/v1/quotations/inquire-price",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": "FHKST01010100",
        },
        params={"FID_COND_MRKT_DIV_CODE": market_code, "FID_INPUT_ISCD": stock_code},
        timeout=10,
    )
    r.raise_for_status()
    return r.json().get("output", {})


def get_current_price_kis(stock_code: str) -> dict:
    """KIS REST로 현재가 조회. session 필드 포함."""
    out = _inquire_price(stock_code)

    kst = datetime.now(_KST)
    session = _session_from_kst(kst)

    # KIS 응답 키는 소문자
    regular_price = int(out.get("stck_prpr") or 0)
    after_price = int(out.get("ovtm_untp_prpr") or 0)
    ref_price = int(out.get("stck_sdpr") or 0)  # 기준가(전일종가 대용)

    if session == "after" and after_price > 0:
        current_price = after_price
        change_amount = int(out.get("ovtm_untp_prdy_vrss") or 0)
        change_pct = float(out.get("ovtm_untp_prdy_ctrt") or 0)
    elif regular_price > 0:
        current_price = regular_price
        change_amount = int(out.get("prdy_vrss") or 0)
        change_pct = float(out.get("prdy_ctrt") or 0)
    else:
        current_price = ref_price
        change_amount = int(out.get("prdy_vrss") or 0)
        change_pct = float(out.get("prdy_ctrt") or 0)

    return {
        "stock_code": stock_code,
        "current_price": current_price,
        "change_pct": change_pct,
        "change_amount": change_amount,
        "open": int(out.get("stck_oprc") or 0),
        "high": int(out.get("stck_hgpr") or 0),
        "low": int(out.get("stck_lwpr") or 0),
        "volume": int(out.get("acml_vol") or 0),
        "date": kst.strftime("%Y-%m-%d"),
        "session": session,
    }


def get_fundamental_kis(stock_code: str) -> dict:
    """KIS REST로 PER/PBR/EPS/BPS/시가총액 조회."""

    def pos(v) -> float | None:
        try:
            f = float(v)
            return f if f > 0 else None
        except (TypeError, ValueError):
            return None

    try:
        out = _inquire_price(stock_code)
        avls = out.get("hts_avls")
        market_cap = int(float(avls) * 1e8) if avls else None
        return {
            "per": pos(out.get("per")),
            "pbr": pos(out.get("pbr")),
            "eps": pos(out.get("eps")),
            "bps": pos(out.get("bps")),
            "div": get_dividend_yield_naver(stock_code),
            "market_cap": market_cap,
        }
    except Exception:
        return {"per": None, "pbr": None, "eps": None, "bps": None, "div": None, "market_cap": None}


# ─── 분봉 차트 ─────────────────────────────────────────────────────────────────

def _fetch_minute_candles_at(stock_code: str, base_hhmmss: str, market_code: str = "J") -> list[dict]:
    """KIS 1분봉 1회 호출 — base_hhmmss 기준 그 이전 30건. 시간 오름차순으로 반환."""
    token = get_access_token()
    r = httpx.get(
        f"{_REST_BASE}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": settings.kis_app_key,
            "appsecret": settings.kis_app_secret,
            "tr_id": "FHKST03010200",
        },
        params={
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": market_code,
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_HOUR_1": base_hhmmss,
            "FID_PW_DATA_INCU_YN": "N",
        },
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    output2 = data.get("output2", []) or []

    candles = []
    for row in output2:
        date_str = (row.get("stck_bsop_date") or "").strip()
        time_str = (row.get("stck_cntg_hour") or "").strip()
        if not date_str or not time_str or len(date_str) != 8 or len(time_str) != 6:
            continue
        try:
            dt = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S").replace(tzinfo=_KST)
            unix_ts = int(dt.timestamp())
            candles.append({
                "time": unix_ts,
                "open": int(row.get("stck_oprc") or 0),
                "high": int(row.get("stck_hgpr") or 0),
                "low": int(row.get("stck_lwpr") or 0),
                "close": int(row.get("stck_prpr") or 0),
                "volume": int(row.get("cntg_vol") or 0),
            })
        except (ValueError, TypeError):
            continue

    candles.sort(key=lambda c: c["time"])
    return candles


def _aggregate_to_n_minute(candles_1m: list[dict], interval_min: int) -> list[dict]:
    """1분봉 리스트를 N분봉으로 OHLCV 집계."""
    if interval_min <= 1 or not candles_1m:
        return candles_1m

    bucket_sec = interval_min * 60
    bucketed: dict[int, dict] = {}
    for c in candles_1m:
        bucket_ts = (c["time"] // bucket_sec) * bucket_sec
        if bucket_ts not in bucketed:
            bucketed[bucket_ts] = {
                "time": bucket_ts,
                "open": c["open"],
                "high": c["high"],
                "low": c["low"],
                "close": c["close"],
                "volume": c["volume"],
            }
        else:
            b = bucketed[bucket_ts]
            b["high"] = max(b["high"], c["high"])
            b["low"] = min(b["low"], c["low"])
            b["close"] = c["close"]
            b["volume"] += c["volume"]
    return sorted(bucketed.values(), key=lambda c: c["time"])


def get_minute_chart_kis(stock_code: str, interval_min: int = 1, market_code: str = "J") -> list[dict]:
    """interval_min 분봉 데이터 반환. 1분봉이면 호출 1회 (30건), 5분봉이면 2회 합산 후 집계 (12건).
    시간은 unix timestamp(초) — frontend lightweight-charts UTCTimestamp 호환."""
    if interval_min == 1:
        # 호출 1회 — 최근 30분
        kst_now = datetime.now(_KST)
        base = kst_now.strftime("%H%M%S")
        return _fetch_minute_candles_at(stock_code, base, market_code)

    # 5분봉: 1분봉 60개 → 5분봉 12개로 집계
    kst_now = datetime.now(_KST)
    base1 = kst_now.strftime("%H%M%S")
    # 두번째 호출은 30분 전 기준 — 그 이전 30분(즉 30~60분 전) 1분봉
    earlier = (kst_now - timedelta(minutes=30)).strftime("%H%M%S")

    all_1m = []
    try:
        all_1m.extend(_fetch_minute_candles_at(stock_code, base1, market_code))
    except Exception:
        pass
    try:
        all_1m.extend(_fetch_minute_candles_at(stock_code, earlier, market_code))
    except Exception:
        pass

    # 중복 제거 (같은 분에 양쪽 호출에서 올 수 있음)
    seen: dict[int, dict] = {}
    for c in all_1m:
        seen[c["time"]] = c
    deduped = sorted(seen.values(), key=lambda c: c["time"])
    return _aggregate_to_n_minute(deduped, interval_min)
