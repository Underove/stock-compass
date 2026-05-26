import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.db.trade_db import get_profile, update_ai_memo
from app.llm.gemini import generate_answer
from app.rag.qa import answer_with_context

logger = logging.getLogger(__name__)
router = APIRouter()

_RISK_LABEL = {"aggressive": "공격적", "neutral": "중립", "defensive": "방어적"}
_HORIZON_LABEL = {"short": "단기", "mid": "중기", "long": "장기"}


def _build_profile_context(profile: dict) -> str | None:
    """투자 성향 dict → LLM 주입용 텍스트. 기본값(neutral/mid/빈 섹터)이면 None."""
    risk = profile.get("risk_level", "neutral")
    horizon = profile.get("horizon", "mid")
    sectors = profile.get("sectors") or []
    memo = profile.get("ai_memo", "")

    is_default = (risk == "neutral" and horizon == "mid" and not sectors and not memo)
    if is_default:
        return None

    lines = [
        f"리스크: {_RISK_LABEL.get(risk, risk)} / 기간: {_HORIZON_LABEL.get(horizon, horizon)}",
    ]
    if sectors:
        lines.append(f"선호 섹터: {', '.join(sectors)}")
    if memo:
        lines.append(f"AI 메모: {memo}")
    return "[사용자 투자 성향]\n" + "\n".join(lines)


def _update_memo_background(username: str, question: str, answer: str) -> None:
    """채팅 후 비동기로 AI 메모 갱신. 실패해도 채팅에 영향 없음."""
    try:
        profile = get_profile(username)
        current_memo = profile.get("ai_memo", "")
        prompt = (
            f"사용자의 투자 성향 메모를 업데이트해주세요. 1~2문장으로만 작성. 별표(*) 금지.\n\n"
            f"현재 메모: {current_memo or '(없음)'}\n\n"
            f"최근 질문: {question}\n"
            f"최근 답변 요약: {answer[:300]}\n\n"
            f"업데이트된 메모 (1~2문장만):"
        )
        new_memo = generate_answer(prompt, temperature=0.5)
        if new_memo and len(new_memo) < 400:
            update_ai_memo(username, new_memo.strip())
    except Exception as e:
        logger.debug("AI 메모 업데이트 실패 (무시): %s", e)


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
def ask(req: AskRequest, bg: BackgroundTasks, username: str = Depends(get_current_user)) -> AskResponse:
    if not req.question.strip():
        raise HTTPException(400, "질문을 입력해주세요")

    profile = get_profile(username)
    profile_ctx = _build_profile_context(profile)

    try:
        result = answer_with_context(
            req.question,
            n_chunks=req.n_chunks,
            username=username,
            profile_context=profile_ctx,
        )
    except Exception as e:
        raise HTTPException(500, f"답변 생성 실패: {type(e).__name__}: {e}")

    bg.add_task(_update_memo_background, username, req.question, result["answer"])

    return AskResponse(
        question=req.question,
        answer=result["answer"],
        sources=[AskSource(**s) for s in result["sources"]],
        companies_synced=[CompanySynced(**c) for c in result.get("companies_synced", [])],
    )
