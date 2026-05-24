from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rag.qa import answer_with_context

router = APIRouter()


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    n_chunks: int = Field(default=5, ge=1, le=10)


class AskSource(BaseModel):
    snippet: str
    label: str
    distance: float


class CompanySynced(BaseModel):
    corp_name: str
    stock_code: str


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[AskSource]
    companies_synced: list[CompanySynced] = []


@router.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    if not req.question.strip():
        raise HTTPException(400, "질문을 입력해주세요")

    try:
        result = answer_with_context(req.question, n_chunks=req.n_chunks)
    except Exception as e:
        raise HTTPException(500, f"답변 생성 실패: {type(e).__name__}: {e}")

    return AskResponse(
        question=req.question,
        answer=result["answer"],
        sources=[AskSource(**s) for s in result["sources"]],
        companies_synced=[CompanySynced(**c) for c in result.get("companies_synced", [])],
    )
