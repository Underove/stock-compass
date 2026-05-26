"""포트폴리오 + DART 공시 + 업로드 자료 교차 분석 엔드포인트."""
import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from app.collectors.krx import get_current_price
from app.collectors.web_search import news_to_context, search_news
from app.db.chroma_client import get_trusted_collection, get_user_uploads_collection
from app.llm.gemini import generate_answer
from app.rag.qa import build_context

router = APIRouter()

PORTFOLIO_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "portfolio.json"

ANALYZE_SYSTEM = """당신은 개인 투자자의 포트폴리오를 분석하는 AI 비서입니다.

아래 [참고 자료]에는 세 가지 유형의 데이터가 섞여 있습니다:
- DART 공시: 금융감독원 공식 자료. 사실로 취급.
- 사용자 업로드: 투자 서적·리포트 등 사용자가 올린 자료. 출처 명시 후 분석 근거로 활용.
- 포트폴리오 시세: 실시간 주가 데이터.

분석 방식:
1. 업로드된 자료에서 투자 기준(선호 섹터, 지표 기준, 주의 사항 등)을 먼저 파악.
2. DART 공시와 현재 시세로 포트폴리오 각 종목의 상태를 점검.
3. 두 가지를 교차해 "업로드 자료의 기준에서 보면 이 종목은 어떤가"를 평가.
4. 구체적이고 솔직하게 의견 제시. 근거는 [자료 N] 형식으로 표기.
5. 미래 수익 보장 표현 금지. 별표 강조 금지. 평문으로만.
6. 전문 용어는 괄호로 쉽게 풀어 설명. 예: 유상증자(회사가 새 주식을 발행해 돈을 모으는 것).
7. 마지막에 각 보유 종목을 한 줄씩 요약 (종목명: 상태 한 줄)."""


def _load_portfolio() -> list[dict]:
    if not PORTFOLIO_FILE.exists():
        return []
    with open(PORTFOLIO_FILE, encoding="utf-8") as f:
        return json.load(f)


def _fetch_prices(items: list[dict]) -> dict[str, dict]:
    prices = {}
    for item in items:
        try:
            prices[item["stock_code"]] = get_current_price(item["stock_code"])
        except Exception:
            pass
    return prices


def _query_collection(collection, question: str, n: int) -> tuple[list[str], list[dict]]:
    if collection.count() == 0:
        return [], []
    r = collection.query(query_texts=[question], n_results=n)
    return (
        r.get("documents", [[]])[0],
        r.get("metadatas", [[]])[0],
    )


class AnalyzeRequest(BaseModel):
    question: str = "내 포트폴리오를 분석해줘"


@router.post("/analyze")
def analyze_portfolio(body: AnalyzeRequest | None = None):
    """포트폴리오 + 공시 + 업로드 자료를 종합해 AI 분석 리포트 생성."""
    question = body.question if body else "내 포트폴리오를 분석해줘"

    # 1. 포트폴리오 + 시세 수집
    items = _load_portfolio()
    prices = _fetch_prices(items) if items else {}

    portfolio_lines = []
    for item in items:
        p = prices.get(item["stock_code"])
        if p:
            pct = round((p["current_price"] - item["buy_price"]) / item["buy_price"] * 100, 2) if item["buy_price"] else 0
            sign = "+" if pct >= 0 else ""
            portfolio_lines.append(
                f"- {item['corp_name']} ({item['stock_code']}): "
                f"보유 {item['quantity']:,}주 · 매수단가 {item['buy_price']:,}원 · "
                f"현재가 {p['current_price']:,}원 · 등락 {sign}{pct}%"
            )
        else:
            portfolio_lines.append(
                f"- {item['corp_name']} ({item['stock_code']}): "
                f"보유 {item['quantity']:,}주 · 매수단가 {item['buy_price']:,}원 · (시세 조회 실패)"
            )

    portfolio_text = "\n".join(portfolio_lines) if portfolio_lines else "포트폴리오가 비어 있습니다."

    # 2. 업로드 자료에서 투자 기준 검색
    analyze_query = f"투자 기준 종목 선정 {question}"
    user_chunks, user_meta = _query_collection(get_user_uploads_collection(), analyze_query, 5)

    # 3. DART 공시에서 보유 종목 관련 정보 검색
    company_names = " ".join(i["corp_name"] for i in items) if items else question
    dart_query = f"{company_names} 공시 실적 재무"
    trusted_chunks, trusted_meta = _query_collection(get_trusted_collection(), dart_query, 5)

    # 4. 종목별 최신 뉴스 검색 (네이버 API 키 있을 때만)
    news_parts = []
    for item in items[:5]:  # 최대 5종목
        news = search_news(f"{item['corp_name']} 주식 뉴스", display=3)
        if news:
            news_parts.append(news_to_context(news, label_prefix=f"{item['corp_name']} 뉴스"))
    news_context = "\n\n---\n\n".join(news_parts)

    # 5. 컨텍스트 조합
    all_chunks = trusted_chunks + user_chunks
    all_meta = (trusted_meta or []) + (user_meta or [])
    rag_context = build_context(all_chunks, all_meta) if all_chunks else "검색된 참고 자료 없음"

    full_context = rag_context
    if news_context:
        full_context += f"\n\n---\n\n{news_context}"

    prompt = f"""[포트폴리오 현황]
{portfolio_text}

[참고 자료]
{full_context}

[요청]
{question}"""

    analysis = generate_answer(prompt, system_instruction=ANALYZE_SYSTEM)

    return {
        "analysis": analysis,
        "portfolio_count": len(items),
        "prices_loaded": len(prices),
        "dart_chunks": len(trusted_chunks),
        "upload_chunks": len(user_chunks),
        "news_loaded": sum(1 for p in news_parts if p),
    }
