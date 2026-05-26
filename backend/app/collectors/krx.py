"""pykrx 기반 한국 주식 시세 수집기."""
from datetime import datetime, timedelta, timezone

from pykrx import stock as krx_stock

_KST = timezone(timedelta(hours=9))


def _now_kst() -> datetime:
    return datetime.now(_KST)


def _trading_date(offset_days: int = 0) -> str:
    """영업일 기준 날짜 문자열 반환 (주말 자동 조정)."""
    d = _now_kst() - timedelta(days=offset_days)
    # 토요일 → -1, 일요일 → -2
    if d.weekday() == 5:
        d -= timedelta(days=1)
    elif d.weekday() == 6:
        d -= timedelta(days=2)
    return d.strftime("%Y%m%d")


def get_current_price(stock_code: str) -> dict:
    """오늘 기준 현재가·등락률·거래량 조회."""
    today = _trading_date()
    df = krx_stock.get_market_ohlcv_by_date(
        (_now_kst() - timedelta(days=5)).strftime("%Y%m%d"),
        today,
        stock_code,
    )
    if df.empty:
        raise ValueError(f"주가 데이터 없음: {stock_code}")

    row = df.iloc[-1]
    # 전일 종가
    prev_close = int(df.iloc[-2]["종가"]) if len(df) >= 2 else int(row["종가"])
    close = int(row["종가"])
    change_pct = round((close - prev_close) / prev_close * 100, 2) if prev_close else 0.0

    return {
        "stock_code": stock_code,
        "current_price": close,
        "change_pct": change_pct,
        "change_amount": close - prev_close,
        "open": int(row["시가"]),
        "high": int(row["고가"]),
        "low": int(row["저가"]),
        "volume": int(row["거래량"]),
        "date": df.index[-1].strftime("%Y-%m-%d"),
    }


def get_chart_data(stock_code: str, days: int = 90) -> list[dict]:
    """최근 N 영업일 OHLCV 캔들 데이터 반환."""
    end = _now_kst()
    start = end - timedelta(days=days + 40)  # 주말·공휴일 여유
    df = krx_stock.get_market_ohlcv_by_date(
        start.strftime("%Y%m%d"),
        end.strftime("%Y%m%d"),
        stock_code,
    )
    if df.empty:
        raise ValueError(f"차트 데이터 없음: {stock_code}")

    result = []
    for date, row in df.tail(days).iterrows():
        result.append(
            {
                "time": date.strftime("%Y-%m-%d"),
                "open": int(row["시가"]),
                "high": int(row["고가"]),
                "low": int(row["저가"]),
                "close": int(row["종가"]),
                "volume": int(row["거래량"]),
            }
        )
    return result


def search_ticker(query: str) -> list[dict]:
    """DART corp_codes 파일에서 종목명 검색 (krx 코드용 래퍼)."""
    import json
    from pathlib import Path

    corp_file = Path(__file__).resolve().parent.parent.parent / "data" / "dart" / "corp_codes.json"
    if not corp_file.exists():
        return []

    with open(corp_file, encoding="utf-8") as f:
        corps = json.load(f)

    query_lower = query.lower()
    results = [
        c for c in corps
        if query_lower in c["corp_name"].lower() and c.get("stock_code")
    ]
    return results[:20]
