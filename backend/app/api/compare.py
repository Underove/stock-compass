"""종목 비교 API."""
import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.collectors.krx import krx_stock
from app.db.trade_db import _conn

router = APIRouter()
_log = logging.getLogger(__name__)
_KST = timezone(timedelta(hours=9))
_METRIC_KEYS = (
    "market_cap", "per", "pbr", "rsi",
    "momentum_20d", "volume_ratio", "foreign_net_buy",
)


@router.get("/compare")
def compare_stocks(codes: str, period: str = "3m"):
    code_list = [c for c in (c.strip() for c in codes.split(",")) if c]
    if len(code_list) != 2:
        raise HTTPException(400, "codes는 정확히 2개여야 합니다")

    _VALID_PERIODS = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}
    if period not in _VALID_PERIODS:
        raise HTTPException(400, "period는 1m/3m/6m/1y 중 하나여야 합니다")
    period_days = _VALID_PERIODS[period]
    end = datetime.now(_KST).date()
    start = end - timedelta(days=period_days)

    result = []
    for code in code_list:
        info = _get_metrics(code)
        corp_name = info.pop("corp_name", None)
        sector = info.pop("sector", None)
        price_series = _get_price_series(code, start, end)
        result.append({
            "stock_code": code,
            "corp_name": corp_name,
            "sector": sector,
            "metrics": info,
            "price_series": price_series,
        })

    return {"stocks": result, "period": period}


def _get_metrics(stock_code: str) -> dict:
    with _conn() as con:
        row = con.execute(
            """SELECT corp_name, sector, market_cap, per, pbr, rsi,
                      momentum_20d, volume_ratio, foreign_net_buy
               FROM screener_snapshot WHERE stock_code=?""",
            (stock_code,),
        ).fetchone()
    if not row:
        return {"corp_name": None, "sector": None, **{k: None for k in _METRIC_KEYS}}
    return {k: row[k] for k in row.keys()}


def _get_price_series(stock_code: str, start: date, end: date) -> list[dict]:
    try:
        df = krx_stock.get_market_ohlcv_by_date(
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), stock_code
        )
        if df.empty:
            return []
        base = int(df.iloc[0]["종가"])
        series = []
        for dt, row in df.iterrows():
            close = int(row["종가"])
            series.append({
                "date": dt.strftime("%Y-%m-%d"),
                "close": close,
                "return_pct": round((close - base) / base * 100, 2) if base else 0.0,
            })
        return series
    except Exception:
        _log.warning("pykrx fetch failed for %s", stock_code, exc_info=True)
        return []
