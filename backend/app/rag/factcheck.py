from app.collectors.dart import ensure_company_synced
from app.db.chroma_client import get_trusted_collection, get_user_uploads_collection
from app.llm.gemini import generate_answer, parse_json_response
from app.rag.qa import build_context, describe_source

MAX_DOC_CHARS = 6000
MAX_COMPANIES = 5
MAX_CLAIMS = 5


def extract_companies_and_claims(text: str) -> dict:
    """문서에서 회사명과 검증 대상 주장들을 LLM으로 추출."""
    truncated = text[:MAX_DOC_CHARS]
    prompt = f"""다음 문서에서 두 가지를 JSON으로 추출하세요.

1. companies: 언급된 한국 상장 회사명만 (배열, 정확한 회사명, 최대 {MAX_COMPANIES}개)
2. claims: 검증이 필요한 핵심 주장 (배열, 각 한 문장, 최대 {MAX_CLAIMS}개)

주장이란 사실관계·수치·시점·결과 등에 대한 단정적 진술입니다.
회사명 또는 주장이 없으면 빈 배열로.

[문서]
{truncated}

JSON 형식만 출력. 다른 설명 금지. 바로 {{ 로 시작.
{{
  "companies": ["..."],
  "claims": ["..."]
}}
"""
    response = generate_answer(prompt, temperature=0.0)
    parsed = parse_json_response(response, default={"companies": [], "claims": []})
    return {
        "companies": parsed.get("companies", [])[:MAX_COMPANIES],
        "claims": parsed.get("claims", [])[:MAX_CLAIMS],
    }


def verify_claim(claim: str, n_chunks: int = 5) -> dict:
    """주장 하나를 trusted 컬렉션과 대조해 검증."""
    trusted = get_trusted_collection()
    if trusted.count() == 0:
        return {
            "verdict": "근거없음",
            "reasoning": "공식 데이터 데이터베이스가 비어있습니다.",
            "sources": [],
        }

    result = trusted.query(query_texts=[claim], n_results=n_chunks)
    chunks = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    if not chunks:
        return {
            "verdict": "근거없음",
            "reasoning": "관련 공식 자료를 찾지 못했습니다.",
            "sources": [],
        }

    context = build_context(chunks, metadatas)
    prompt = f"""다음 주장이 공식 자료에 의해 뒷받침되는지 판단하세요.

판정 기준:
- 지지: 공식 자료가 주장과 일치하는 사실을 명시함.
- 모순: 다음 중 하나에 해당.
  (1) 공식 자료가 주장과 반대되는 사실을 명시함.
  (2) 자료에서 드러난 회사의 실제 사업 영역과 주장이 명백히 무관함.
      (예: 반도체·전자 회사에 대한 신약 임상 주장, 자동차 회사에 대한 외식 사업 주장 등)
- 근거없음: 공식 자료에 관련 정보가 부분적이거나, 결정적으로 판단하기 부족함.

판단 절차:
1. 먼저 [공식 자료]를 보고 회사의 주요 사업 영역을 파악.
2. 그 사업 영역과 [주장]의 내용을 비교.
3. 명백한 일치/반대/사업 영역 불일치 신호가 있으면 "지지"/"모순"으로 단정.
4. 신호가 약하거나 일부만 일치하면 "근거없음".

reasoning은 2~3문장. 회사의 사업 영역을 언급한 뒤 판정 근거를 설명.

[주장]
{claim}

[공식 자료]
{context}

JSON 형식만 출력. 마크다운 코드블록 금지. 별표 굵기 금지. 바로 {{ 로 시작.
{{
  "verdict": "지지" | "모순" | "근거없음",
  "reasoning": "2~3문장의 판단 이유"
}}
"""
    response = generate_answer(prompt, temperature=0.0)
    parsed = parse_json_response(
        response,
        default={"verdict": "근거없음", "reasoning": "판단 실패"},
    )

    sources = [
        {
            "snippet": chunk[:200] + ("…" if len(chunk) > 200 else ""),
            "label": describe_source(meta),
            "distance": dist,
        }
        for chunk, meta, dist in zip(chunks, metadatas, distances)
    ]
    return {
        "verdict": parsed.get("verdict", "근거없음"),
        "reasoning": parsed.get("reasoning", ""),
        "sources": sources,
    }


def compute_signal(claim_verdicts: list[dict]) -> tuple[str, int]:
    """판정 결과들을 종합해 신호등 색상과 0~100 점수 산출."""
    if not claim_verdicts:
        return "yellow", 50

    total = len(claim_verdicts)
    supported = sum(1 for v in claim_verdicts if v["verdict"] == "지지")
    contradicted = sum(1 for v in claim_verdicts if v["verdict"] == "모순")
    unknown = total - supported - contradicted

    score = (supported * 100 + unknown * 50) / total
    if contradicted > 0:
        score -= (contradicted / total) * 30

    score_int = max(0, min(100, int(round(score))))

    if score_int >= 75:
        signal = "green"
    elif score_int >= 40:
        signal = "yellow"
    else:
        signal = "red"

    return signal, score_int


def _load_upload_text(upload_id: str) -> str:
    """upload_id에 해당하는 청크들을 chunk_index 순으로 결합."""
    user_col = get_user_uploads_collection()
    result = user_col.get(where={"upload_id": upload_id})
    documents = result.get("documents") or []
    metadatas = result.get("metadatas") or []
    if not documents:
        raise ValueError(f"upload_id '{upload_id}' 에 해당하는 자료를 찾을 수 없습니다")

    indexed = sorted(
        zip(documents, metadatas),
        key=lambda pair: (pair[1] or {}).get("chunk_index", 0),
    )

    text = ""
    for doc, _ in indexed:
        if len(text) + len(doc) > MAX_DOC_CHARS:
            break
        text += doc + "\n"
    return text


def factcheck_upload(upload_id: str) -> dict:
    """업로드된 자료에 대해 팩트체크 파이프라인 실행."""
    full_text = _load_upload_text(upload_id)

    extracted = extract_companies_and_claims(full_text)
    company_names = extracted["companies"]
    claims = extracted["claims"]

    companies_synced: list[dict] = []
    for cname in company_names:
        try:
            company = ensure_company_synced(cname)
        except Exception:
            company = None
        if company:
            companies_synced.append(company)

    claim_results: list[dict] = []
    for claim in claims:
        try:
            v = verify_claim(claim)
        except Exception as e:
            v = {
                "verdict": "근거없음",
                "reasoning": f"검증 중 오류 발생: {type(e).__name__}",
                "sources": [],
            }
        claim_results.append({"claim": claim, **v})

    signal, score = compute_signal(claim_results)

    return {
        "upload_id": upload_id,
        "signal": signal,
        "score": score,
        "companies_detected": [
            {"name": c["corp_name"], "stock_code": c["stock_code"]}
            for c in companies_synced
        ],
        "claims": claim_results,
    }
