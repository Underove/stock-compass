from app.collectors.dart import ensure_companies_from_text
from app.collectors.web_search import news_to_context, search_news
from app.db.chroma_client import get_trusted_collection, get_user_uploads_collection
from app.llm.gemini import generate_answer

SYSTEM_INSTRUCTION = """당신은 한국 주식 정보를 분석하는 AI 비서입니다.

자료 출처:
- "DART 공시" 또는 "DART 공시 본문": 금융감독원 공식 공시. 사실(fact)로 취급.
- "사용자 업로드": 사용자가 올린 투자 자료·리포트·서적. 내용을 분석 근거로 활용하되 출처 명시.

답변 규칙:
1. [참고 자료]의 내용을 근거로 분석. 근거 사용 시 [자료 N] 형식으로 본문에 표기.
2. 자료에 없는 내용은 "자료에서 확인되지 않음"이라고 밝힘.
3. DART 공시는 사실로 인용. 사용자 업로드는 "올린 자료에 따르면"으로 출처 명시.
4. 두 출처가 충돌하면 충돌을 명시하고 공시를 우선.
5. 금융 용어는 반드시 괄호로 풀어 설명. 예: PER(주가를 주당순이익으로 나눈 값). 호칭 금지. 담백한 톤.
6. 별표(*) 금지. 소제목(##) 금지. 평문과 번호 목록만 허용.
7. 종목·섹터 분석은 근거 기반으로 자유롭게 제시. 미래 수익 보장 표현 금지.
8. 종목 추천·분석 요청에는 보유 데이터(공시, 시세, 업로드 자료)를 최대한 활용해 구체적으로 답변.

답변 형식:
- 첫 문장에 핵심 결론 또는 요점을 먼저 제시.
- 단락은 빈 줄로 구분. 전체 4단락 이내로 간결하게.
- 3개 이상 항목 나열 시 번호(1. 2. 3.) 사용.
- 마지막 단락에 투자자가 직접 확인해볼 포인트 1~2개를 제시."""


def describe_source(meta: dict | None) -> str:
    """청크 메타데이터를 사람이 읽기 좋은 라벨로 변환."""
    if not meta:
        return "출처 미상"
    source_type = meta.get("source_type", "")
    if source_type in ("dart_disclosure", "dart_disclosure_body"):
        company = meta.get("company_name", "")
        report = meta.get("report_nm", "")
        date = meta.get("rcept_dt", "")
        kind = "공시 본문" if source_type == "dart_disclosure_body" else "공시"
        return f"DART {kind} · {company} · {report} ({date})"
    if source_type == "dart_financial":
        company = meta.get("company_name", "")
        year = meta.get("year", "")
        return f"DART 재무제표 · {company} · {year}년"
    if source_type == "user_upload":
        return f"사용자 업로드 · {meta.get('filename', '')}"
    return meta.get("filename", "") or source_type or "출처 미상"


def build_context(chunks: list[str], metadatas: list[dict]) -> str:
    """LLM 프롬프트에 넣을 [자료 N] 형식의 컨텍스트 문자열 생성."""
    parts = []
    for i, (chunk, meta) in enumerate(zip(chunks, metadatas), start=1):
        parts.append(f"[자료 {i} — 출처: {describe_source(meta)}]\n{chunk}")
    return "\n\n---\n\n".join(parts)


def _query_collection(collection, question: str, n: int) -> tuple[list[str], list[dict], list[float]]:
    if collection.count() == 0:
        return [], [], []
    r = collection.query(query_texts=[question], n_results=n)
    return (
        r.get("documents", [[]])[0],
        r.get("metadatas", [[]])[0],
        r.get("distances", [[]])[0],
    )


def answer_with_context(question: str, n_chunks: int = 5) -> dict:
    """trusted 우선 쿼터 + user_uploads 보조로 검색 → 거리순 정렬 → LLM 답변.

    질문에 새 회사명이 있으면 검색 전에 자동 sync.
    """
    newly_synced: list[dict] = []
    try:
        _, newly_synced = ensure_companies_from_text(question, max_new_syncs=2)
    except Exception:
        pass  # 자동 sync 실패는 답변을 막지 않음

    user_chunks, user_meta, user_dist = _query_collection(
        get_user_uploads_collection(), question, n_chunks
    )
    trusted_chunks, trusted_meta, trusted_dist = _query_collection(
        get_trusted_collection(), question, n_chunks
    )

    if not user_chunks and not trusted_chunks:
        return {
            "answer": "아직 분석 가능한 자료가 없습니다. PDF를 업로드하거나 DART 공시를 수집해주세요.",
            "sources": [],
        }

    # 쿼터: trusted를 더 많이 (3:2) — 채팅은 보통 사실 확인용
    if trusted_chunks and user_chunks:
        trusted_take = min((n_chunks * 2 + 2) // 3, len(trusted_chunks))
        user_take = min(n_chunks - trusted_take, len(user_chunks))
    elif trusted_chunks:
        trusted_take = min(n_chunks, len(trusted_chunks))
        user_take = 0
    else:
        trusted_take = 0
        user_take = min(n_chunks, len(user_chunks))

    picked_chunks = trusted_chunks[:trusted_take] + user_chunks[:user_take]
    picked_meta = trusted_meta[:trusted_take] + user_meta[:user_take]
    picked_dist = trusted_dist[:trusted_take] + user_dist[:user_take]

    order = sorted(range(len(picked_chunks)), key=lambda i: picked_dist[i])
    chunks = [picked_chunks[i] for i in order]
    metadatas = [picked_meta[i] or {} for i in order]
    distances = [picked_dist[i] for i in order]

    # 웹 뉴스 검색 (네이버 API 키 있을 때만)
    news_items = search_news(f"{question} 주식", display=3)
    news_ctx = news_to_context(news_items, label_prefix="웹 뉴스")

    rag_ctx = build_context(chunks, metadatas)
    full_ctx = f"{rag_ctx}\n\n---\n\n{news_ctx}" if news_ctx else rag_ctx

    prompt = f"[참고 자료]\n{full_ctx}\n\n[질문]\n{question}"
    answer = generate_answer(prompt, system_instruction=SYSTEM_INSTRUCTION)

    sources = [
        {
            "snippet": chunk[:200] + ("…" if len(chunk) > 200 else ""),
            "label": describe_source(meta),
            "distance": dist,
        }
        for chunk, meta, dist in zip(chunks, metadatas, distances)
    ]
    return {
        "answer": answer,
        "sources": sources,
        "companies_synced": [
            {"corp_name": c["corp_name"], "stock_code": c["stock_code"]}
            for c in newly_synced
        ],
    }
