from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.factcheck import factcheck_upload

router = APIRouter()


class FactcheckRequest(BaseModel):
    upload_id: str = Field(..., min_length=1)


class FactcheckSource(BaseModel):
    snippet: str
    label: str
    distance: float


class ClaimResult(BaseModel):
    claim: str
    verdict: str
    reasoning: str
    sources: list[FactcheckSource]


class CompanyDetected(BaseModel):
    name: str
    stock_code: str


class FactcheckResponse(BaseModel):
    upload_id: str
    signal: str
    score: int
    companies_detected: list[CompanyDetected]
    claims: list[ClaimResult]


@router.post("/factcheck/run", response_model=FactcheckResponse)
def run_factcheck(req: FactcheckRequest) -> FactcheckResponse:
    try:
        result = factcheck_upload(req.upload_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"팩트체크 실패: {type(e).__name__}: {e}")

    return FactcheckResponse(
        upload_id=result["upload_id"],
        signal=result["signal"],
        score=result["score"],
        companies_detected=[CompanyDetected(**c) for c in result["companies_detected"]],
        claims=[
            ClaimResult(
                claim=c["claim"],
                verdict=c["verdict"],
                reasoning=c["reasoning"],
                sources=[FactcheckSource(**s) for s in c["sources"]],
            )
            for c in result["claims"]
        ],
    )
