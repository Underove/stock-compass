"""KOSPI / KOSDAQ 실시간 지수 + 장 상태."""
import datetime
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

_TICKERS = {"KOSPI": "1001", "KOSDAQ": "2001"}


def _get_market_status() -> dict:
    """한국 주식시장 개폐장 상태 (KST 기준)."""
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(kst)
    weekday = now.weekday()  # 0=월, 6=일
    h, m = now.hour, now.minute
    minutes = h * 60 + m

    if weekday >= 5:
        return {"status": "closed", "label": "주말 휴장"}
    if minutes < 9 * 60:
        return {"status": "pre", "label": "장 개장 전"}
    if minutes <= 15 * 60 + 30:
        return {"status": "open", "label": "장 운영 중"}
    return {"status": "closed", "label": "장 마감"}


@router.get("/market/indices")
def get_market_indices():
    """KOSPI·KOSDAQ 지수값 + 장 상태 반환."""
    from pykrx import stock

    end = datetime.date.today()
    start = end - datetime.timedelta(days=14)  # 주말·공휴일 대비 충분히
    indices: dict = {}

    for name, ticker in _TICKERS.items():
        try:
            df = stock.get_index_ohlcv_by_date(
                start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), ticker
            )
            if df is None or df.empty:
                continue
            df = df.sort_index()
            close = float(df.iloc[-1]["종가"])
            prev_close = float(df.iloc[-2]["종가"]) if len(df) >= 2 else close
            change = close - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0
            indices[name] = {
                "name": name,
                "value": round(close, 2),
                "change": round(change, 2),
                "change_pct": round(change_pct, 2),
            }
        except Exception as e:
            logger.warning("지수 조회 실패 (%s): %s", name, e)

    return {"indices": indices, "market_status": _get_market_status()}
