import html
import io
import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

KEY_FINANCIAL_ACCOUNTS = {"매출액", "영업이익", "당기순이익", "자산총계", "부채총계", "자본총계"}

import httpx

from app.config import settings
from app.parsers.pdf_parser import chunk_text

DART_BASE_URL = "https://opendart.fss.or.kr/api"
CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "dart"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CORP_CODES_FILE = CACHE_DIR / "corp_codes.json"
CORP_CODES_TTL_DAYS = 30

_corp_codes_cache: list[dict] | None = None


def _require_key() -> str:
    if not settings.dart_api_key:
        raise RuntimeError("DART_API_KEY가 .env에 설정되지 않았습니다")
    return settings.dart_api_key


def _cache_is_fresh(path: Path, ttl_days: int) -> bool:
    if not path.exists():
        return False
    age_seconds = datetime.now().timestamp() - path.stat().st_mtime
    return age_seconds < ttl_days * 86400


def download_corp_codes(force: bool = False) -> list[dict]:
    """DART에서 모든 상장사 corp_code 매핑 다운로드. 메모리 + 디스크 캐시(30일)."""
    global _corp_codes_cache
    if not force and _corp_codes_cache is not None:
        return _corp_codes_cache
    companies: list[dict]
    if not force and _cache_is_fresh(CORP_CODES_FILE, CORP_CODES_TTL_DAYS):
        with open(CORP_CODES_FILE, encoding="utf-8") as f:
            companies = json.load(f)
        _corp_codes_cache = companies
        return companies

    key = _require_key()
    res = httpx.get(
        f"{DART_BASE_URL}/corpCode.xml",
        params={"crtfc_key": key},
        timeout=60,
    )
    res.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(res.content)) as z:
        with z.open("CORPCODE.xml") as xml_file:
            tree = ET.parse(xml_file)

    companies = []
    for node in tree.getroot().findall("list"):
        stock_code = (node.findtext("stock_code") or "").strip()
        if not stock_code:
            continue
        companies.append(
            {
                "corp_code": (node.findtext("corp_code") or "").strip(),
                "corp_name": (node.findtext("corp_name") or "").strip(),
                "stock_code": stock_code,
                "modify_date": (node.findtext("modify_date") or "").strip(),
            }
        )

    with open(CORP_CODES_FILE, "w", encoding="utf-8") as f:
        json.dump(companies, f, ensure_ascii=False, indent=2)
    _corp_codes_cache = companies
    return companies


def find_company(query: str) -> dict | None:
    """회사명 또는 종목코드로 검색. 정확 매치 우선, 부분 매치 fallback."""
    query = query.strip()
    if not query:
        return None
    companies = download_corp_codes()

    if query.isdigit():
        for c in companies:
            if c["stock_code"] == query:
                return c

    for c in companies:
        if c["corp_name"] == query:
            return c

    for c in companies:
        if query in c["corp_name"]:
            return c

    return None


def fetch_recent_disclosures(
    corp_code: str,
    days: int = 90,
    max_count: int = 30,
) -> list[dict]:
    """corp_code 기준 최근 공시 목록 가져오기."""
    key = _require_key()
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    res = httpx.get(
        f"{DART_BASE_URL}/list.json",
        params={
            "crtfc_key": key,
            "corp_code": corp_code,
            "bgn_de": start.strftime("%Y%m%d"),
            "end_de": end.strftime("%Y%m%d"),
            "page_count": max_count,
        },
        timeout=30,
    )
    res.raise_for_status()
    data = res.json()

    status = data.get("status")
    if status == "013":
        return []
    if status != "000":
        raise RuntimeError(f"DART API error: {data.get('message', data)}")
    return data.get("list", [])


def _build_disclosure_doc(company: dict, d: dict) -> tuple[str, str, dict]:
    rcept_no = d.get("rcept_no", "")
    report_nm = d.get("report_nm", "")
    text = (
        f"회사: {company['corp_name']} (종목코드 {company['stock_code']})\n"
        f"공시명: {report_nm}\n"
        f"제출자: {d.get('flr_nm', '')}\n"
        f"접수일: {d.get('rcept_dt', '')}\n"
        f"비고: {d.get('rm', '')}"
    )
    metadata = {
        "source_type": "dart_disclosure",
        "company_name": company["corp_name"],
        "stock_code": company["stock_code"],
        "corp_code": company["corp_code"],
        "rcept_no": rcept_no,
        "report_nm": report_nm,
        "rcept_dt": d.get("rcept_dt", ""),
        "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
    }
    return text, f"dart_{rcept_no}", metadata


def _decode_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _strip_xml_to_text(xml_bytes: bytes) -> str:
    """DART 공시 XML 바이트에서 본문 텍스트만 추출 (태그 제거 + 공백 정규화)."""
    text = _decode_bytes(xml_bytes)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_disclosure_body(rcept_no: str) -> str:
    """rcept_no로 공시 본문 ZIP을 받아 텍스트로 변환. 실패 시 빈 문자열."""
    if not rcept_no:
        return ""
    key = _require_key()
    try:
        res = httpx.get(
            f"{DART_BASE_URL}/document.xml",
            params={"crtfc_key": key, "rcept_no": rcept_no},
            timeout=60,
        )
        res.raise_for_status()
    except Exception:
        return ""

    try:
        with zipfile.ZipFile(io.BytesIO(res.content)) as z:
            xml_names = [n for n in z.namelist() if n.lower().endswith(".xml")]
            if not xml_names:
                return ""
            with z.open(xml_names[0]) as f:
                return _strip_xml_to_text(f.read())
    except (zipfile.BadZipFile, KeyError):
        return ""


def _build_disclosure_body_chunks(
    disclosure: dict, company: dict
) -> list[tuple[str, str, dict]]:
    """공시 본문 다운로드 후 800자 청크로 분할. 본문이 짧으면 빈 리스트."""
    rcept_no = disclosure.get("rcept_no", "")
    body = fetch_disclosure_body(rcept_no)
    if len(body) < 200:
        return []

    chunks = chunk_text(body, chunk_size=800, overlap=150)
    return [
        (
            chunk,
            f"dart_{rcept_no}_body_{i}",
            {
                "source_type": "dart_disclosure_body",
                "company_name": company["corp_name"],
                "stock_code": company["stock_code"],
                "corp_code": company["corp_code"],
                "rcept_no": rcept_no,
                "report_nm": disclosure.get("report_nm", ""),
                "rcept_dt": disclosure.get("rcept_dt", ""),
                "chunk_index": i,
                "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}",
            },
        )
        for i, chunk in enumerate(chunks)
    ]


def sync_company_disclosures(
    company: dict,
    days: int = 90,
    with_body: bool = False,
    body_limit: int = 10,
    with_financials: bool = False,
) -> dict:
    """corp_code 기준 공시를 가져와 trusted 컬렉션에 upsert.

    with_body=True 면 공시 본문도 다운로드해서 청킹·저장 (body_limit개까지).
    with_financials=True 면 연간 재무제표도 저장.
    """
    from app.db.chroma_client import get_trusted_collection  # 지연 임포트로 순환 회피

    disclosures = fetch_recent_disclosures(company["corp_code"], days=days)
    triples: list[tuple[str, str, dict]] = []

    if disclosures:
        triples = [_build_disclosure_doc(company, d) for d in disclosures]
        if with_body:
            for d in disclosures[:body_limit]:
                body_triples = _build_disclosure_body_chunks(d, company)
                if body_triples:
                    triples.extend(body_triples)

    bodies_stored = sum(
        1 for t in triples if t[2].get("source_type") == "dart_disclosure_body"
    )

    if with_financials:
        year = datetime.now().year - 1
        fin_items = fetch_financial_statements(company["corp_code"], year)
        if not fin_items:
            fin_items = fetch_financial_statements(company["corp_code"], year - 1)
            if fin_items:
                year -= 1
        if fin_items:
            triples.append(_build_financial_doc(company, fin_items, year))

    if not triples:
        return {"fetched": len(disclosures), "stored": 0, "bodies_stored": 0, "sample_titles": []}

    documents = [t[0] for t in triples]
    ids = [t[1] for t in triples]
    metadatas = [t[2] for t in triples]

    get_trusted_collection().upsert(documents=documents, ids=ids, metadatas=metadatas)

    return {
        "fetched": len(disclosures),
        "stored": len(documents),
        "bodies_stored": bodies_stored,
        "sample_titles": [d.get("report_nm", "") for d in disclosures[:5]],
    }


def is_company_in_trusted(stock_code: str) -> bool:
    """trusted에 해당 종목의 청크가 하나라도 있는지 확인 (메타·본문 무관)."""
    from app.db.chroma_client import get_trusted_collection

    trusted = get_trusted_collection()
    result = trusted.get(where={"stock_code": stock_code}, limit=1)
    return bool(result.get("ids"))


def has_body_in_trusted(stock_code: str) -> bool:
    """trusted에 해당 종목의 본문 청크가 있는지 확인."""
    from app.db.chroma_client import get_trusted_collection

    trusted = get_trusted_collection()
    try:
        result = trusted.get(
            where={
                "$and": [
                    {"stock_code": stock_code},
                    {"source_type": "dart_disclosure_body"},
                ]
            },
            limit=1,
        )
        return bool(result.get("ids"))
    except Exception:
        return False


def ensure_company_synced(query: str, days: int = 90) -> dict | None:
    """회사명/종목코드로 검색해 본문·재무제표가 없으면 sync. 매칭된 company dict 반환."""
    company = find_company(query)
    if not company:
        return None
    needs_body = not has_body_in_trusted(company["stock_code"])
    needs_financials = not has_financials_in_trusted(company["stock_code"])
    if needs_body or needs_financials:
        try:
            sync_company_disclosures(
                company, days=days,
                with_body=needs_body,
                with_financials=needs_financials,
            )
        except Exception:
            return company
    return company


def detect_companies_in_text(text: str, max_results: int = 5) -> list[dict]:
    """텍스트에 등장하는 상장사명을 longest-match 우선으로 탐지."""
    if not text:
        return []
    companies = download_corp_codes()
    matched: list[dict] = []
    seen_codes: set[str] = set()
    for c in sorted(companies, key=lambda x: -len(x["corp_name"])):
        name = c["corp_name"]
        if len(name) < 3 or c["stock_code"] in seen_codes:
            continue
        if name in text:
            matched.append(c)
            seen_codes.add(c["stock_code"])
            if len(matched) >= max_results:
                break
    return matched


def fetch_financial_statements(corp_code: str, year: int) -> list[dict]:
    """연간 사업보고서에서 주요 재무 계정 가져오기. 실패 시 빈 리스트."""
    key = _require_key()
    try:
        res = httpx.get(
            f"{DART_BASE_URL}/fnlttSinglAcnt.json",
            params={
                "crtfc_key": key,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": "11011",
            },
            timeout=30,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("status") != "000":
            return []
        return [
            item for item in data.get("list", [])
            if item.get("account_nm") in KEY_FINANCIAL_ACCOUNTS
            and item.get("fs_div") == "CFS"  # 연결 재무제표 우선
        ] or [
            item for item in data.get("list", [])
            if item.get("account_nm") in KEY_FINANCIAL_ACCOUNTS
        ]
    except Exception:
        return []


def _build_financial_doc(company: dict, items: list[dict], year: int) -> tuple[str, str, dict]:
    lines = [f"회사: {company['corp_name']} (종목코드 {company['stock_code']}) {year}년 연간 주요 재무 지표 (단위: 백만원)\n"]
    for item in items:
        nm = item.get("account_nm", "")
        curr = item.get("thstrm_amount", "-")
        prev = item.get("frmtrm_amount", "-")
        lines.append(f"- {nm}: 당기({year}) {curr} / 전기({year - 1}) {prev}")
    text = "\n".join(lines)
    doc_id = f"dart_financial_{company['corp_code']}_{year}"
    metadata = {
        "source_type": "dart_financial",
        "company_name": company["corp_name"],
        "stock_code": company["stock_code"],
        "corp_code": company["corp_code"],
        "year": year,
        "url": "https://dart.fss.or.kr",
    }
    return text, doc_id, metadata


def has_financials_in_trusted(stock_code: str) -> bool:
    """trusted에 해당 종목의 재무제표 청크가 있는지 확인."""
    from app.db.chroma_client import get_trusted_collection

    trusted = get_trusted_collection()
    try:
        result = trusted.get(
            where={
                "$and": [
                    {"stock_code": stock_code},
                    {"source_type": "dart_financial"},
                ]
            },
            limit=1,
        )
        return bool(result.get("ids"))
    except Exception:
        return False


def ensure_companies_from_text(
    text: str, max_new_syncs: int = 2
) -> tuple[list[dict], list[dict]]:
    """텍스트에서 회사명을 감지하고 본문·재무제표가 없는 회사를 최대 max_new_syncs개까지 sync.

    Returns (감지된 모든 회사, 이번에 새로 sync된 회사) 튜플.
    """
    detected = detect_companies_in_text(text)
    newly_synced: list[dict] = []
    new_syncs = 0
    for company in detected:
        needs_body = not has_body_in_trusted(company["stock_code"])
        needs_financials = not has_financials_in_trusted(company["stock_code"])
        if not needs_body and not needs_financials:
            continue
        if new_syncs >= max_new_syncs:
            break
        try:
            sync_company_disclosures(
                company, days=90,
                with_body=needs_body,
                with_financials=needs_financials,
            )
            newly_synced.append(company)
            new_syncs += 1
        except Exception:
            pass
    return detected, newly_synced
