from app.collectors.dart import ensure_companies_from_text
from app.db.chroma_client import get_trusted_collection, get_user_uploads_collection
from app.llm.gemini import generate_with_tools

SYSTEM_INSTRUCTION = """당신은 한국 주식 정보를 분석하는 AI 비서입니다.

자료 출처:
- "DART 공시" 또는 "DART 공시 본문": 금융감독원 공식 공시. 사실(fact)로 취급.
- "사용자 업로드": 사용자가 올린 투자 자료·리포트·서적. 내용을 분석 근거로 활용하되 출처 명시.
- 도구(Function) 조회 결과: 실시간 시세·포트폴리오·뉴스·기술지표·공시. 사실로 취급.

수치 그라운딩 규칙 (필수):
- 가격·수익률·재무 수치는 반드시 도구 조회 결과 또는 [참고 자료]에서 인용. 직접 수치를 추측하거나 생성하지 않음.
- 도구 호출이 실패하거나 결과에 error 필드가 있으면 "현재 조회할 수 없습니다"로 명시. 추측 금지.
- 출처 없는 미래 수익 예측·보장 표현 금지.

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


def retrieve_for_answer(
    question: str,
    n_chunks: int = 5,
    profile_context: str | None = None,
) -> dict:
    """검색·정렬·프롬프트 빌드만 수행. 답변 생성은 호출자가 처리.

    반환값: { prompt, sources, companies_synced, chunks, metadatas }
    """
    newly_synced: list[dict] = []
    try:
        _, newly_synced = ensure_companies_from_text(question, max_new_syncs=2)
    except Exception:
        pass

    user_chunks, user_meta, user_dist = _query_collection(
        get_user_uploads_collection(), question, n_chunks
    )
    trusted_chunks, trusted_meta, trusted_dist = _query_collection(
        get_trusted_collection(), question, n_chunks
    )

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

    rag_ctx = build_context(chunks, metadatas) if chunks else ""
    parts = [p for p in [profile_context, rag_ctx] if p]
    full_ctx = "\n\n---\n\n".join(parts) if parts else ""

    if full_ctx:
        prompt = f"[참고 자료]\n{full_ctx}\n\n[질문]\n{question}"
    else:
        prompt = f"[질문]\n{question}"

    sources = [
        {
            "snippet": chunk[:200] + ("…" if len(chunk) > 200 else ""),
            "label": describe_source(meta),
            "distance": dist,
        }
        for chunk, meta, dist in zip(chunks, metadatas, distances)
    ]
    companies_synced = [
        {"corp_name": c["corp_name"], "stock_code": c["stock_code"]}
        for c in newly_synced
    ]
    return {
        "prompt": prompt,
        "sources": sources,
        "companies_synced": companies_synced,
    }


def answer_with_context(
    question: str,
    n_chunks: int = 5,
    username: str | None = None,
    profile_context: str | None = None,
) -> dict:
    """동기 RAG + tool-calling LLM 답변."""
    retrieved = retrieve_for_answer(question, n_chunks=n_chunks, profile_context=profile_context)
    answer = generate_with_tools(
        retrieved["prompt"],
        system_instruction=SYSTEM_INSTRUCTION,
        username=username,
    )
    return {
        "answer": answer,
        "sources": retrieved["sources"],
        "companies_synced": retrieved["companies_synced"],
    }
