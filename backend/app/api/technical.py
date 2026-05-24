"""기술적 지표 조회 엔드포인트."""
from fastapi import APIRouter, HTTPException

from app.collectors.ta_engine import analyze

router = APIRouter()


@router.get("/portfolio/technical/{stock_code}")
def get_technical(stock_code: str):
    """MA·RSI·MACD·볼린저밴드·지지저항·52주 고저 반환."""
    try:
        result = analyze(stock_code)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    if result.get("error"):
        raise HTTPException(status_code=422, detail=result["error"])
    return result
