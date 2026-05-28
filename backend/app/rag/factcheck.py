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
    SYSTEM = f"""역할: 한국 주식 관련 문서에서 검증 대상 추출자.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록 금지.

{{
  "companies": ["문서에 등장한 한국 상장 회사명 배열, 최대 {MAX_COMPANIES}개"],
  "claims": ["검증이 필요한 단정적 주장 한 문장씩, 최대 {MAX_CLAIMS}개"]
}}

기준:
- companies: 문서에 직접 등장한 정확한 회사명만. 추측·유사명 금지.
- claims: 사실관계·수치·시점·결과에 대한 단정. "X가 Y하다", "X 매출이 Z원" 같은 검증 가능한 진술.
- 의견·전망·추측은 제외 ("좋아 보인다", "오를 것 같다").
- 해당 없으면 빈 배열."""
    prompt = f"[문서]\n{truncated}"
    response = generate_answer(
        prompt, system_instruction=SYSTEM,
        temperature=0.0, max_tokens=500, json_mode=True,
    )
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
    SYSTEM = """역할: DART 공시 기반 주장 검증자.

출력은 아래 JSON 객체 하나. 그 외 텍스트·코드블록·별표(*) 금지.

{"verdict": "지지 | 모순 | 근거없음", "reasoning": "2~3문장 판단 근거"}

판정 기준:
- 지지: 공식 자료가 주장과 일치하는 사실을 명시.
- 모순: 다음 중 하나.
  (1) 공식 자료가 반대 사실을 명시.
  (2) 자료에서 드러난 회사 사업 영역과 주장이 명백히 무관 (예: 반도체 회사에 대한 신약 임상 주장).
- 근거없음: 자료 정보가 부분적이거나 결정 불가.

판단 절차:
1. 먼저 [공식 자료]에서 회사 사업 영역 파악.
2. 그 영역과 [주장]을 비교.
3. 명백한 일치/반대/영역 불일치만 '지지'/'모순'. 신호 약하면 '근거없음'.

reasoning 형식:
- 첫 문장: 회사 사업 영역 1줄 요약 (자료 인용).
- 둘째~셋째 문장: 주장과의 일치/불일치 판단 근거.

그라운딩 (필수):
- [공식 자료]에 없는 사실 생성 금지. 추측·일반화 금지.
- 일반 상식이나 외부 지식 사용 금지. 오직 제공된 자료만."""
    prompt = f"[주장]\n{claim}\n\n[공식 자료]\n{context}"
    response = generate_answer(
        prompt, system_instruction=SYSTEM,
        temperature=0.0, max_tokens=400, json_mode=True,
    )
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


def _load_upload_text(upload_id: str, username: str) -> str:
    """본인 upload_id에 해당하는 청크들을 chunk_index 순으로 결합 (멀티유저 격리)."""
    user_col = get_user_uploads_collection()
    result = user_col.get(where={"upload_id": upload_id, "username": username})
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


def factcheck_upload(upload_id: str, username: str) -> dict:
    """본인 업로드 자료에 대해 팩트체크 파이프라인 실행 (멀티유저 격리)."""
    full_text = _load_upload_text(upload_id, username)

    extracted = extract_companies_and_claims(full_text)
    company_names = extracted["companies"]
    claims = extracted["claims"]

    # 회사별 DART 동기화는 서로 독립 + cold sync가 매우 무거움(본문 다운로드·임베딩) → 병렬
    def _sync_one(cname: str) -> dict | None:
        try:
            return ensure_company_synced(cname)
        except Exception:
            return None

    if company_names:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(5, len(company_names))) as ex:
            synced = list(ex.map(_sync_one, company_names))
        companies_synced = [c for c in synced if c]
    else:
        companies_synced = []

    # 주장 검증은 서로 독립이라 병렬 처리 (순차 시 LLM 호출이 누적돼 매우 느림)
    def _verify_one(claim: str) -> dict:
        try:
            return {"claim": claim, **verify_claim(claim)}
        except Exception as e:
            return {
                "claim": claim,
                "verdict": "근거없음",
                "reasoning": f"검증 중 오류 발생: {type(e).__name__}",
                "sources": [],
            }

    if claims:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(5, len(claims))) as ex:
            claim_results = list(ex.map(_verify_one, claims))
    else:
        claim_results = []

    signal, score = compute_signal(claim_results)

    # 결과 영속 — 채팅 답변 그라운딩 + 투명성 (실패해도 응답엔 영향 없음)
    try:
        from app.db.trade_db import save_factcheck_results
        save_factcheck_results(upload_id, claim_results, username)
    except Exception:
        pass

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
