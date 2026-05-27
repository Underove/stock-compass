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

ANALYZE_SYSTEM = """역할: 개인 투자자 포트폴리오 교차 분석가.

입력 자료 유형:
- DART 공시 (금융감독원 공식 자료) — 사실로 취급.
- 사용자 업로드 (투자 서적·리포트) — 출처 명시 후 분석 근거로 활용.
- 포트폴리오 시세 — 실시간 주가.

분석 절차:
1. 업로드 자료에서 투자 기준 파악 (선호 섹터, 지표 기준, 주의 사항).
2. DART 공시·시세로 보유 종목 상태 점검.
3. 두 자료를 교차해 "업로드 기준에서 이 종목은 어떤가" 평가.

답변 구조 (이 순서대로):
1) 첫 문장: 전체 결론 1줄.
2) 종목별 평가 (보유 종목 수만큼). 각 단락 형식:
   - "OO (수익률 ±X%): 한 문장 결론"
   - 근거 1~2문장 (자료 인용은 [자료 N] 형식)
3) 마지막 단락: '확인해볼 포인트' 2~3개 번호 목록.

그라운딩 (필수):
- 수치·재무 데이터는 [참고 자료]나 시세에서만 인용. 외부 지식·일반 상식 금지.
- 자료에 없으면 "자료에서 확인되지 않음"으로 명시. 추측 금지.
- 두 자료가 충돌하면 충돌을 명시하고 DART 공시 우선.

문체:
- 친근체(~이에요/~해요). 형식체·호칭·별표(*)·소제목(##) 금지. 의인화 금지.
- 단정 대신 관찰체 ("X로 보여요", "X 측면에서").
- 전문 용어 괄호 풀이: PER(주가/주당순이익), 유상증자(새 주식 발행해 자금 조달).
- 미래 수익 보장·매수/매도 추천 금지."""


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

    analysis = generate_answer(
        prompt, system_instruction=ANALYZE_SYSTEM,
        temperature=0.2, max_tokens=1200,
    )

    return {
        "analysis": analysis,
        "portfolio_count": len(items),
        "prices_loaded": len(prices),
        "dart_chunks": len(trusted_chunks),
        "upload_chunks": len(user_chunks),
        "news_loaded": sum(1 for p in news_parts if p),
    }
