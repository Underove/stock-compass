import asyncio
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.db.trade_db import get_profile, update_ai_memo
from app.llm.gemini import generate_answer
from app.rag.qa import SYSTEM_INSTRUCTION, answer_with_context, retrieve_for_answer

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


_MEMO_SYSTEM = """역할: 사용자 투자 성향 메모 업데이트 작성자.

출력 형식: 메모 본문 1~2문장만. JSON·라벨·코드블록·별표 금지.

업데이트 방식:
- 기존 메모가 있으면 새 질문에서 드러난 관심사·성향을 자연스럽게 통합.
- 기존 메모가 없으면 질문·답변에서 보이는 관심 영역을 짧게 요약.
- 사용자가 명시한 사실만 반영. 추측·일반화 금지.

문체:
- 친근체(~이에요/~해요). 형식체·호칭·별표(*) 금지.
- 단정 대신 관찰체. 100자 이내."""


def _update_memo_background(username: str, question: str, answer: str) -> None:
    """채팅 후 비동기로 AI 메모 갱신. 실패해도 채팅에 영향 없음."""
    try:
        profile = get_profile(username)
        current_memo = profile.get("ai_memo", "")
        prompt = (
            f"[현재 메모]\n{current_memo or '(없음)'}\n\n"
            f"[최근 질문]\n{question}\n\n"
            f"[답변 요약]\n{answer[:300]}"
        )
        new_memo = generate_answer(
            prompt, system_instruction=_MEMO_SYSTEM,
            temperature=0.3, max_tokens=200,
        )
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


def _sse(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/ask/stream")
async def ask_stream(
    req: AskRequest,
    bg: BackgroundTasks,
    username: str = Depends(get_current_user),
):
    """SSE 스트리밍 답변. 이벤트: metadata → token(다수) → done | error."""
    if not req.question.strip():
        raise HTTPException(400, "질문을 입력해주세요")

    profile = get_profile(username)
    profile_ctx = _build_profile_context(profile)

    async def event_stream():
        full_answer = ""
        try:
            retrieved = await asyncio.to_thread(
                retrieve_for_answer,
                req.question,
                n_chunks=req.n_chunks,
                profile_context=profile_ctx,
            )
        except Exception as e:
            yield _sse("error", {"message": f"자료 검색 실패: {type(e).__name__}"})
            return

        # 1) 메타데이터 (출처·자동수집 회사) 즉시 전송
        yield _sse("metadata", {
            "sources": retrieved["sources"],
            "companies_synced": retrieved["companies_synced"],
        })

        # 2) 토큰 스트리밍 (제너레이터를 to_thread로 wrap)
        from app.llm.openai_llm import generate_with_tools_stream

        def _producer(queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
            try:
                for ev_type, data in generate_with_tools_stream(
                    retrieved["prompt"],
                    system_instruction=SYSTEM_INSTRUCTION,
                    username=username,
                ):
                    asyncio.run_coroutine_threadsafe(queue.put((ev_type, data)), loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put(("error", str(e))), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(("__end__", "")), loop)

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, _producer, queue, loop)

        while True:
            ev_type, data = await queue.get()
            if ev_type == "__end__":
                break
            if ev_type == "token":
                yield _sse("token", {"text": data})
            elif ev_type == "done":
                full_answer = data
                yield _sse("done", {})
                break
            elif ev_type == "error":
                yield _sse("error", {"message": data})
                break

        if full_answer:
            bg.add_task(_update_memo_background, username, req.question, full_answer)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
