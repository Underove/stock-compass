# backend/app/collectors/screener_collector.py
"""pykrx 기반 전 종목 기본적 지표 + TA 배치 수집."""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# KRX 업종 → 앱 섹터 매핑
KRX_SECTOR_MAP: dict[str, str] = {
    "전기전자":   "반도체",
    "의약품":     "바이오·제약",
    "운수장비":   "자동차",
    "화학":       "화학·소재",
    "비금속광물": "화학·소재",
    "철강금속":   "화학·소재",
    "금융업":     "금융·보험",
    "서비스업":   "IT·플랫폼",
    "통신업":     "IT·플랫폼",
    "유통업":     "소비재·유통",
    "음식료품":   "소비재·유통",
    "섬유의복":   "소비재·유통",
    "기계":       "조선·방산",
    "운수창고업": "조선·방산",
    "게임":       "게임·엔터",
    "방송·통신":  "게임·엔터",
}


def _latest_trading_date() -> str:
    """오늘 기준 최근 영업일 문자열 (yyyymmdd)."""
    d = datetime.now()
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def fetch_all_fundamentals() -> list[dict]:
    """전 종목 기본적 지표 + 섹터 수집. 반환: list of screener_snapshot 행 dict."""
    from pykrx import stock as krx

    date = _latest_trading_date()
    logger.info("[스크리너] 기본적 지표 수집 시작 (기준일: %s)", date)

    # 섹터 역방향 맵 {ticker: app_sector}
    sector_map: dict[str, str] = {}
    for krx_sector, app_sector in KRX_SECTOR_MAP.items():
        try:
            tickers = krx.get_market_sector_ticker_list(date, market="KOSPI", sector=krx_sector)
            for t in tickers:
                sector_map[t] = app_sector
        except Exception as e:
            logger.warning("[스크리너] 섹터 조회 실패 (%s): %s", krx_sector, e)

    # 기본적 지표 배치 (PER, PBR)
    try:
        fund_df = krx.get_market_fundamental_by_ticker(date, market="KOSPI")
    except Exception as e:
        logger.error("[스크리너] 기본적 지표 배치 조회 실패: %s", e)
        return []

    # 시가총액 배치
    try:
        cap_df = krx.get_market_cap_by_ticker(date, market="KOSPI")
    except Exception as e:
        logger.error("[스크리너] 시가총액 배치 조회 실패: %s", e)
        cap_df = None

    result: list[dict] = []
    for ticker in fund_df.index:
        try:
            per_val = fund_df.loc[ticker, "PER"] if "PER" in fund_df.columns else None
            pbr_val = fund_df.loc[ticker, "PBR"] if "PBR" in fund_df.columns else None
            per = float(per_val) if per_val and float(per_val) > 0 else None
            pbr = float(pbr_val) if pbr_val and float(pbr_val) > 0 else None

            mcap_raw = int(cap_df.loc[ticker, "시가총액"]) if cap_df is not None and ticker in cap_df.index else 0
            mcap_eok = mcap_raw // 100_000_000  # 원 → 억 원

            corp_name = krx.get_market_ticker_name(ticker)
            if not corp_name:
                continue

            momentum = _compute_momentum_20d(ticker)

            result.append({
                "stock_code":   ticker,
                "corp_name":    corp_name,
                "sector":       sector_map.get(ticker, "기타"),
                "market_cap":   mcap_eok,
                "per":          per,
                "pbr":          pbr,
                "momentum_20d": momentum,
                "rsi":          None,
                "ma_status":    None,
                "has_ta":       0,
            })
        except Exception as e:
            logger.debug("[스크리너] %s 처리 실패: %s", ticker, e)

    logger.info("[스크리너] 기본적 지표 수집 완료: %d종목", len(result))
    return result


def _compute_momentum_20d(stock_code: str) -> float | None:
    """최근 20거래일 수익률(%)."""
    try:
        from app.collectors.krx import get_chart_data
        candles = get_chart_data(stock_code, days=25)
        if len(candles) < 20:
            return None
        price_now = candles[-1]["close"]
        price_20d_ago = candles[-20]["close"]
        if price_20d_ago == 0:
            return None
        return round((price_now - price_20d_ago) / price_20d_ago * 100, 2)
    except Exception:
        return None


def compute_ta_for_top_n(n: int = 300) -> list[dict]:
    """시총 상위 n개 종목의 RSI·MA 상태 계산. 반환: list of {stock_code, rsi, ma_status}."""
    from app.collectors.ta_engine import analyze
    from app.db.trade_db import get_top_market_cap_codes

    codes = get_top_market_cap_codes(n)
    logger.info("[스크리너] TA 배치 계산 시작: %d종목", len(codes))

    results: list[dict] = []
    for i, code in enumerate(codes):
        try:
            ta = analyze(code)
            if ta.get("error"):
                continue
            results.append({
                "stock_code": code,
                "rsi":        ta.get("rsi"),
                "ma_status":  ta.get("cross_5_20"),
            })
        except Exception as e:
            logger.debug("[스크리너] TA 계산 실패 (%s): %s", code, e)
        if (i + 1) % 50 == 0:
            logger.info("[스크리너] TA 진행: %d/%d", i + 1, len(codes))

    logger.info("[스크리너] TA 배치 완료: %d종목", len(results))
    return results
