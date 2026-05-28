"""포트폴리오 + DART 공시 + 업로드 자료 교차 분석 엔드포인트.

지갑(보유종목)은 portfolio._load(username)로 본인 것만, 업로드 자료는
username 메타 필터로 본인 것만 검색 — 멀티유저 격리.
출력은 브리핑과 동일하게 구조화 JSON + 참고 자료(출처) 목록.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.api.portfolio import _get_price, _load
from app.collectors.web_search import news_to_context, search_news
from app.config import settings
from app.db.chroma_client import get_trusted_collection, get_user_uploads_collection
from app.llm.gemini import generate_answer, parse_json_response
from app.rag.qa import build_context, describe_source

router = APIRouter()

ANALYZE_SYSTEM = """역할: 개인 투자자 포트폴리오 심층 분석가.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록 금지.

{
  "summary": "포트폴리오 전반 평가 1~2문장 (보유 구성·수익 흐름 + 자료에서 드러난 핵심)",
  "holdings": [
    {"corp_name": "종목명", "verdict": "긍정 | 중립 | 주의", "change_note": "평가손익 +X.X%", "comment": "한 문장 결론 + 근거"}
  ],
  "action_items": ["투자자가 직접 확인해볼 포인트 1", "포인트 2"]
}

작성 기준:
- holdings: [포트폴리오 현황]의 보유 종목마다 하나씩. corp_name·change_note는 입력값을 그대로 인용(변경·추정 금지).
- verdict: 긍정=자료가 우호적 / 주의=자료가 부정적이거나 리스크 신호 / 중립=판단 근거 부족.
- comment: [참고 자료](DART 공시·업로드 자료)와 시세를 근거로. 자료에 없으면 "공식 자료에서 확인되지 않아 시세 흐름 위주로 보여요" 식으로 명시.
- action_items: 2~3개. 구체적 확인 행위. 투자 권유·매수/매도 추천 금지.

그라운딩 (필수):
- 수치·재무 데이터는 [참고 자료]나 시세에서만 인용. 외부 지식·일반 상식·추측 금지.
- 두 자료가 충돌하면 DART 공시를 우선.
- 미래 수익 보장 표현 금지.

문체:
- 친근체(~이에요/~해요). 형식체·호칭·별표(*)·소제목(##) 금지. 의인화 금지.
- 단정 대신 관찰체 ("X로 보여요"). 전문 용어는 괄호 풀이. 큰따옴표 안엔 작은따옴표 사용."""


def _fetch_prices(items: list[dict]) -> dict[str, dict]:
    prices = {}
    for item in items:
        try:
            prices[item["stock_code"]] = _get_price(item["stock_code"])
        except Exception:
            pass
    return prices


def _query_collection(collection, question: str, n: int, where: dict | None = None) -> tuple[list[str], list[dict]]:
    if collection.count() == 0:
        return [], []
    r = collection.query(query_texts=[question], n_results=n, where=where)
    return (
        r.get("documents", [[]])[0],
        r.get("metadatas", [[]])[0],
    )


def _snip(text: str, n: int = 160) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:n] + ("…" if len(text) > n else "")


def _build_sources(
    trusted_docs: list[str], trusted_meta: list[dict],
    user_docs: list[str], user_meta: list[dict],
    news_items: list[dict],
) -> list[dict]:
    """검색에 사용된 청크들을 출처 목록으로 (중복 제거 + 조회 링크 포함)."""
    sources: list[dict] = []
    seen: set = set()

    for doc, m in zip(user_docs, user_meta):
        m = m or {}
        key = ("upload", m.get("upload_id") or m.get("filename"))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "type": "upload",
            "label": describe_source(m),
            "snippet": _snip(doc),
            "url": None,
            "upload_id": m.get("upload_id"),
            "filename": m.get("filename"),
        })

    for doc, m in zip(trusted_docs, trusted_meta):
        m = m or {}
        key = ("dart", m.get("rcept_no") or m.get("url") or describe_source(m))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "type": "dart",
            "label": describe_source(m),
            "snippet": _snip(doc),
            "url": m.get("url"),
            "upload_id": None,
            "filename": None,
        })

    for it in news_items:
        url = it.get("url")
        key = ("news", url or it.get("title"))
        if key in seen:
            continue
        seen.add(key)
        sources.append({
            "type": "news",
            "label": it.get("title", "")[:80],
            "snippet": "",
            "url": url,
            "upload_id": None,
            "filename": None,
        })

    return sources[:8]


class AnalyzeRequest(BaseModel):
    question: str = "내 포트폴리오를 분석해줘"


@router.post("/analyze")
def analyze_portfolio(body: AnalyzeRequest | None = None, username: str = Depends(get_current_user)):
    """본인 포트폴리오 + 공시 + 업로드 자료를 종합해 구조화 AI 분석 생성."""
    question = body.question if body else "내 포트폴리오를 분석해줘"

    items = _load(username)
    if not items:
        return {
            "summary": "포트폴리오에 종목이 없어요. 종목을 추가하면 AI 분석을 받을 수 있어요.",
            "holdings": [], "action_items": [], "sources": [],
            "portfolio_count": 0, "upload_chunks": 0, "dart_chunks": 0, "news_loaded": 0,
        }

    # 1. 본인 포트폴리오 + 시세
    prices = _fetch_prices(items)
    portfolio_lines = []
    for item in items:
        p = prices.get(item["stock_code"])
        if p and p.get("current_price"):
            pct = round((p["current_price"] - item["buy_price"]) / item["buy_price"] * 100, 2) if item["buy_price"] else 0
            sign = "+" if pct >= 0 else ""
            portfolio_lines.append(
                f"- {item['corp_name']} ({item['stock_code']}): "
                f"보유 {item['quantity']:,}주 · 매수단가 {item['buy_price']:,}원 · "
                f"현재가 {p['current_price']:,}원 · 평가손익 {sign}{pct}%"
            )
        else:
            portfolio_lines.append(
                f"- {item['corp_name']} ({item['stock_code']}): "
                f"보유 {item['quantity']:,}주 · 매수단가 {item['buy_price']:,}원 · (시세 조회 실패)"
            )
    portfolio_text = "\n".join(portfolio_lines)

    # 2. 본인 업로드 자료 (username 격리)
    analyze_query = f"투자 기준 종목 선정 {question}"
    user_docs, user_meta = _query_collection(
        get_user_uploads_collection(), analyze_query, 5, where={"username": username}
    )

    # 3. DART 공시
    company_names = " ".join(i["corp_name"] for i in items)
    dart_query = f"{company_names} 공시 실적 재무"
    trusted_docs, trusted_meta = _query_collection(get_trusted_collection(), dart_query, 5)

    # 4. 종목별 최신 뉴스 (네이버 키 있을 때만)
    news_items: list[dict] = []
    for item in items[:5]:
        news = search_news(f"{item['corp_name']} 주식 뉴스", display=2)
        news_items.extend(news[:2])

    # 5. 컨텍스트 조합 (LLM 입력)
    all_docs = trusted_docs + user_docs
    all_meta = (trusted_meta or []) + (user_meta or [])
    rag_context = build_context(all_docs, all_meta) if all_docs else "검색된 참고 자료 없음"
    full_context = rag_context
    if news_items:
        full_context += "\n\n---\n\n" + news_to_context(news_items)

    prompt = f"""[포트폴리오 현황]
{portfolio_text}

[참고 자료]
{full_context}

[요청]
{question}"""

    try:
        raw = generate_answer(
            prompt, system_instruction=ANALYZE_SYSTEM,
            temperature=0.2, max_tokens=1200, json_mode=True,
            model=settings.openai_model_pro,
        )
        sections = parse_json_response(raw, default={})
    except Exception:
        sections = {}

    summary = sections.get("summary") if isinstance(sections, dict) else None
    holdings = sections.get("holdings") if isinstance(sections, dict) else None
    action_items = sections.get("action_items") if isinstance(sections, dict) else None

    return {
        "summary": summary or "분석을 생성하지 못했어요. 잠시 후 다시 시도해주세요.",
        "holdings": holdings if isinstance(holdings, list) else [],
        "action_items": action_items if isinstance(action_items, list) else [],
        "sources": _build_sources(trusted_docs, trusted_meta, user_docs, user_meta, news_items),
        "portfolio_count": len(items),
        "upload_chunks": len(user_docs),
        "dart_chunks": len(trusted_docs),
        "news_loaded": len(news_items),
    }
