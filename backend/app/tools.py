"""Gemini Function Calling 도구 정의 + 실행 로직 (read-only, 5개)."""
import logging

from google.genai import types

logger = logging.getLogger(__name__)

# ─── 포트폴리오 + 시세 helpers ────────────────────────────────────────────────

def _get_price(stock_code: str) -> dict:
    from app.api.portfolio import _get_price as portfolio_get_price
    return portfolio_get_price(stock_code)


def _load_portfolio(username: str) -> list[dict]:
    from app.api.portfolio import _load
    return _load(username)


def _search_news(query: str, display: int = 3) -> list[dict]:
    from app.collectors.web_search import search_news
    return search_news(query, display=display)


def _ta_analyze(stock_code: str) -> dict:
    from app.collectors.ta_engine import analyze
    return analyze(stock_code)


def _dart_disclosures(corp_name: str) -> list[dict]:
    from app.collectors.dart import download_corp_codes, fetch_recent_disclosures
    companies = download_corp_codes()
    match = next((c for c in companies if corp_name in c.get("corp_name", "")), None)
    if not match:
        return []
    disclosures = fetch_recent_disclosures(match["corp_code"], days=90, max_count=3)
    return [
        {
            "report_nm": d.get("report_nm", ""),
            "rcept_dt": d.get("rcept_dt", ""),
            "flr_nm": d.get("flr_nm", ""),
            "url": f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={d.get('rcept_no', '')}",
        }
        for d in disclosures[:3]
    ]


# ─── FunctionDeclaration 목록 ────────────────────────────────────────────────

TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_stock_price",
        description="종목코드로 주식 현재가·등락률·거래량을 조회한다. 특정 종목 가격이 필요할 때 호출.",
        parameters={
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "KRX 종목코드 6자리. 예: 005930(삼성전자), 000660(SK하이닉스)",
                },
            },
            "required": ["stock_code"],
        },
    ),
    types.FunctionDeclaration(
        name="get_portfolio",
        description="사용자의 보유 포트폴리오 전체를 조회한다. 종목별 현재가·손익·수량 포함. 포트폴리오 관련 질문 시 반드시 호출.",
        parameters={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    types.FunctionDeclaration(
        name="search_recent_news",
        description="네이버 뉴스에서 최근 뉴스 3건을 검색한다. 최신 이슈·시장 동향 질문 시 호출.",
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "검색 질의. 예: '삼성전자 실적', 'KOSPI 오늘'",
                },
            },
            "required": ["query"],
        },
    ),
    types.FunctionDeclaration(
        name="get_technical_indicators",
        description="종목의 RSI·MACD·이동평균(MA5/20/60)·볼린저밴드 등 기술적 지표를 조회한다. 기술적 분석 질문 시 호출.",
        parameters={
            "type": "object",
            "properties": {
                "stock_code": {
                    "type": "string",
                    "description": "KRX 종목코드 6자리",
                },
            },
            "required": ["stock_code"],
        },
    ),
    types.FunctionDeclaration(
        name="get_dart_disclosures",
        description="DART에서 회사명으로 최근 공시 3건을 조회한다. 공시·IR·재무 관련 최신 정보가 필요할 때 호출.",
        parameters={
            "type": "object",
            "properties": {
                "corp_name": {
                    "type": "string",
                    "description": "회사명. 예: '삼성전자', 'SK하이닉스'",
                },
            },
            "required": ["corp_name"],
        },
    ),
]

GEMINI_TOOLS = [types.Tool(function_declarations=TOOL_DECLARATIONS)]


# ─── 도구 실행 dispatcher ────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, username: str) -> dict:
    """도구 이름과 인자로 실제 함수를 실행하고 결과 dict를 반환."""
    try:
        if name == "get_stock_price":
            stock_code = args.get("stock_code", "")
            if not stock_code:
                return {"error": "stock_code 필수"}
            data = _get_price(stock_code)
            return {
                "stock_code": stock_code,
                "current_price": data.get("current_price"),
                "change_pct": data.get("change_pct"),
                "change_amount": data.get("change_amount"),
                "volume": data.get("volume"),
                "session": data.get("session"),
            }

        if name == "get_portfolio":
            items = _load_portfolio(username)
            result = []
            for item in items[:15]:
                try:
                    price_data = _get_price(item["stock_code"])
                    cp = price_data.get("current_price", 0)
                    bp = item.get("buy_price", 0)
                    qty = item.get("quantity", 0)
                    pnl_pct = ((cp - bp) / bp * 100) if bp else 0
                    pnl_amt = (cp - bp) * qty
                    result.append({
                        "corp_name": item["corp_name"],
                        "stock_code": item["stock_code"],
                        "buy_price": bp,
                        "current_price": cp,
                        "quantity": qty,
                        "pnl_pct": round(pnl_pct, 2),
                        "pnl_amount": pnl_amt,
                    })
                except Exception:
                    result.append({
                        "corp_name": item["corp_name"],
                        "stock_code": item["stock_code"],
                        "error": "시세 조회 불가",
                    })
            return {"items": result, "count": len(result)}

        if name == "search_recent_news":
            query = args.get("query", "")
            if not query:
                return {"error": "query 필수"}
            news = _search_news(query, display=3)
            return {"items": news, "count": len(news)}

        if name == "get_technical_indicators":
            stock_code = args.get("stock_code", "")
            if not stock_code:
                return {"error": "stock_code 필수"}
            ta = _ta_analyze(stock_code)
            return ta

        if name == "get_dart_disclosures":
            corp_name = args.get("corp_name", "")
            if not corp_name:
                return {"error": "corp_name 필수"}
            disclosures = _dart_disclosures(corp_name)
            return {"items": disclosures, "count": len(disclosures)}

        return {"error": f"알 수 없는 도구: {name}"}

    except Exception as e:
        logger.warning("Tool %s 실행 실패: %s", name, e)
        return {"error": f"조회 실패: {type(e).__name__}"}
