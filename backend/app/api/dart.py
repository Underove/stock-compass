from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.collectors.dart import find_company, sync_company_disclosures

router = APIRouter()


class DartSyncRequest(BaseModel):
    query: str = Field(..., min_length=1, description="회사명 또는 종목코드 (예: '삼성전자', '005930')")
    days: int = Field(default=90, ge=1, le=365)
    with_body: bool = Field(default=False, description="공시 본문도 다운로드 (느림)")


class DartSyncResponse(BaseModel):
    company: dict
    fetched: int
    stored: int
    bodies_stored: int
    sample_titles: list[str]


@router.post("/dart/sync", response_model=DartSyncResponse)
def sync_dart(req: DartSyncRequest) -> DartSyncResponse:
    try:
        company = find_company(req.query)
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    if not company:
        raise HTTPException(404, f"DART에서 '{req.query}' 회사를 찾을 수 없습니다")

    try:
        result = sync_company_disclosures(company, days=req.days, with_body=req.with_body)
    except Exception as e:
        raise HTTPException(502, f"DART 조회/저장 실패: {type(e).__name__}: {e}")

    return DartSyncResponse(
        company=company,
        fetched=result["fetched"],
        stored=result["stored"],
        bodies_stored=result["bodies_stored"],
        sample_titles=result["sample_titles"],
    )
