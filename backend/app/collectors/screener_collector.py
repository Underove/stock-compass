# backend/app/collectors/screener_collector.py
"""KIS REST + Naver Finance 기반 전 종목 기본적 지표 + TA 배치 수집."""
import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# KIS bstp_kor_isnm → 앱 섹터 매핑 (먼저 정확히 매칭, 그 다음 부분 매칭)
# KIS bstp_kor_isnm 실제 반환값 기준 매핑
_KIS_SECTOR_MAP: dict[str, str] = {
    # 반도체·전자
    "전기·전자":      "반도체",
    "반도체":         "반도체",
    "디스플레이":     "반도체",
    "전자부품":       "반도체",
    # 바이오·제약
    "제약":           "바이오·제약",
    "의약품":         "바이오·제약",
    "의료·정밀기기":  "바이오·제약",
    "바이오":         "바이오·제약",
    # 자동차
    "운송장비·부품":  "자동차",
    "운수장비":       "자동차",
    "자동차":         "자동차",
    # 금융
    "금융":           "금융·보험",
    "금융업":         "금융·보험",
    "은행":           "금융·보험",
    "보험":           "금융·보험",
    "증권":           "금융·보험",
    # IT·플랫폼
    "IT 서비스":      "IT·플랫폼",
    "IT서비스":       "IT·플랫폼",
    "소프트웨어":     "IT·플랫폼",
    "서비스업":       "IT·플랫폼",
    "통신업":         "IT·플랫폼",
    "통신":           "IT·플랫폼",
    "인터넷":         "IT·플랫폼",
    # 게임·엔터
    "게임":           "게임·엔터",
    "엔터테인먼트":   "게임·엔터",
    "미디어":         "게임·엔터",
    "방송":           "게임·엔터",
    "오락·문화":      "게임·엔터",
    "오락":           "게임·엔터",
    # 화학·소재
    "화학":           "화학·소재",
    "정유":           "화학·소재",
    "비금속광물":     "화학·소재",
    "철강·금속":      "화학·소재",
    "철강금속":       "화학·소재",
    "소재":           "화학·소재",
    # 조선·방산
    "조선":           "조선·방산",
    "방위산업":       "조선·방산",
    "기계":           "조선·방산",
    "항공":           "조선·방산",
    "운수·창고":      "조선·방산",
    # 소비재·유통
    "유통업":         "소비재·유통",
    "유통":           "소비재·유통",
    "음식료품":       "소비재·유통",
    "음식료":         "소비재·유통",
    "섬유의복":       "소비재·유통",
    "음료":           "소비재·유통",
    "일반서비스":     "소비재·유통",
    "숙박음식":       "소비재·유통",
    "종이목재":       "소비재·유통",
    "섬유·의류":      "소비재·유통",
    # 화학·소재 (추가)
    "금속":           "화학·소재",
    "비철금속":       "화학·소재",
    "비금속":         "화학·소재",
    "광업":           "화학·소재",
    # 조선·방산 (추가)
    "기계·장비":      "조선·방산",
    "운송·창고":      "조선·방산",
    "운수·창고":      "조선·방산",
    # 건설·인프라 (신규)
    "건설":           "건설·인프라",
    "건설업":         "건설·인프라",
    "부동산":         "건설·인프라",
    "리츠":           "건설·인프라",
    "인프라투용":     "건설·인프라",
    # 에너지·유틸리티 (신규)
    "전기·가스":      "에너지·유틸리티",
    "전기가스업":     "에너지·유틸리티",
    "에너지":         "에너지·유틸리티",
    "전력":           "에너지·유틸리티",
    "가스":           "에너지·유틸리티",
    # 2차전지·전기차 (KIS는 별도 분류 없음 → 회사명 키워드로 보정)
    "2차전지":        "2차전지·전기차",
    "이차전지":       "2차전지·전기차",
}

_DART_CORP_CODES = Path(__file__).resolve().parent.parent.parent / "data" / "dart" / "corp_codes.json"


def _load_dart_codes() -> list[dict]:
    """DART corp_codes.json에서 종목 코드+이름 목록 반환."""
    if not _DART_CORP_CODES.exists():
        return []
    with open(_DART_CORP_CODES, encoding="utf-8") as f:
        return json.load(f)


def _kis_sector_to_app(sector_name: str) -> str:
    """KIS bstp_kor_isnm → 앱 섹터 문자열 매핑."""
    if not sector_name:
        return "기타"
    # 정확히 일치하는 키 우선
    if sector_name in _KIS_SECTOR_MAP:
        return _KIS_SECTOR_MAP[sector_name]
    # 부분 포함 fallback
    for key, app_sector in _KIS_SECTOR_MAP.items():
        if key in sector_name:
            return app_sector
    return "기타"


def _naver_batch_info(codes: list[str]) -> dict[str, dict]:
    """네이버 금융 polling API로 시가총액+거래소코드 배치 조회.
    반환: {stock_code: {"market_cap": 억원, "exch": "KS"|"KQ", "name": 종목명}}
    """
    result: dict[str, dict] = {}
    batch_size = 100
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko",
    }
    for i in range(0, len(codes), batch_size):
        batch = codes[i : i + batch_size]
        codes_str = ",".join(batch)
        try:
            r = httpx.get(
                f"https://polling.finance.naver.com/api/realtime/domestic/stock/{codes_str}",
                headers=headers,
                timeout=10,
            )
            if r.status_code != 200:
                continue
            items = r.json().get("datas") or []
            if isinstance(items, dict):
                items = list(items.values())
            for item in items:
                code = str(item.get("itemCode") or "").zfill(6)
                if not code:
                    continue
                raw_cap_str = item.get("marketValueFullRaw") or "0"
                exch = (item.get("stockExchangeType") or {}).get("code", "")
                name = item.get("stockName", "")
                try:
                    cap = int(str(raw_cap_str).replace(",", "")) // 100_000_000
                except (ValueError, TypeError):
                    cap = 0
                result[code] = {"market_cap": cap, "exch": exch, "name": name}
        except Exception as e:
            logger.debug("[스크리너] 네이버 배치 실패 (%d~): %s", i, e)
        time.sleep(0.1)
    return result


def fetch_all_fundamentals() -> list[dict]:
    """전 종목 기본적 지표 + 섹터 수집. 반환: list of screener_snapshot 행 dict."""
    from app.collectors.kis_rest import _inquire_price

    # 파일이 없으면 DART API에서 자동 다운로드 (Railway 최초 배포 대응)
    try:
        from app.collectors.dart import download_corp_codes
        corps = download_corp_codes()
    except Exception:
        corps = _load_dart_codes()
    if not corps:
        logger.error("[스크리너] DART corp_codes 로드/다운로드 실패")
        return []

    all_codes = [c["stock_code"] for c in corps if c.get("stock_code")]
    corp_name_map = {c["stock_code"]: c["corp_name"] for c in corps if c.get("stock_code")}

    logger.info("[스크리너] 네이버 배치 정보 조회: %d종목", len(all_codes))
    naver_info = _naver_batch_info(all_codes)
    # KS=KOSPI→J, KQ=KOSDAQ→Q, 나머지→J fallback
    exch_to_kis = {"KS": "J", "KQ": "Q"}

    logger.info("[스크리너] KIS 기본적 지표 조회: %d종목 (KOSPI+KOSDAQ 전 종목)", len(naver_info))

    result: list[dict] = []
    codes_list = list(naver_info.keys())
    for i, code in enumerate(codes_list):
        info = naver_info[code]
        market_code = exch_to_kis.get(info["exch"], "J")
        try:
            out = _inquire_price(code, market_code)
            per = _pos(out.get("per"))
            pbr = _pos(out.get("pbr"))
            avls = out.get("hts_avls")
            market_cap = int(float(avls)) if avls else info["market_cap"]

            sector_raw = out.get("bstp_kor_isnm") or ""
            sector = _kis_sector_to_app(sector_raw)
            corp_name = corp_name_map.get(code) or info["name"] or code

            if any(kw in corp_name for kw in (
                "SDI", "에너지솔루션", "배터리", "이차전지", "2차전지", "LFP",
                "양극재", "음극재", "전해질", "분리막", "퓨처엠", "엘앤에프",
                "코스모신소재", "에코프로비엠", "에코프로머티", "에코프로HN",
            )):
                sector = "2차전지·전기차"

            momentum = _compute_momentum_20d(code)

            result.append({
                "stock_code":   code,
                "corp_name":    corp_name,
                "sector":       sector,
                "market_cap":   market_cap,
                "per":          per,
                "pbr":          pbr,
                "momentum_20d": momentum,
                "rsi":          None,
                "ma_status":    None,
                "has_ta":       0,
            })
        except Exception as e:
            logger.debug("[스크리너] %s 처리 실패: %s", code, e)

        # KIS 요청 레이트 리밋: 초당 ~15건
        if (i + 1) % 15 == 0:
            time.sleep(1)
        if (i + 1) % 100 == 0:
            logger.info("[스크리너] 진행: %d/%d (수집: %d)", i + 1, len(codes_list), len(result))

    logger.info("[스크리너] 기본적 지표 수집 완료: %d종목", len(result))
    return result


def _pos(v) -> float | None:
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _compute_momentum_20d(stock_code: str) -> float | None:
    """최근 20거래일 수익률(%)."""
    try:
        from app.collectors.krx import get_chart_data
        candles = get_chart_data(stock_code, days=25)
        if len(candles) < 20:
            return None
        price_now = candles[-1]["close"]
        price_20d_ago = candles[-20]["close"]
        if price_20d_ago == 0:
            return None
        return round((price_now - price_20d_ago) / price_20d_ago * 100, 2)
    except Exception:
        return None


def compute_ta_for_top_n(n: int = 2000) -> list[dict]:
    """시총 상위 n개 종목의 RSI·MA 상태 계산. 반환: list of {stock_code, rsi, ma_status}."""
    from app.collectors.ta_engine import analyze
    from app.db.trade_db import get_top_market_cap_codes

    codes = get_top_market_cap_codes(n)
    logger.info("[스크리너] TA 배치 계산 시작: %d종목", len(codes))

    results: list[dict] = []
    for i, code in enumerate(codes):
        try:
            ta = analyze(code)
            if ta.get("error"):
                continue
            results.append({
                "stock_code":   code,
                "rsi":          ta.get("rsi"),
                "ma_status":    ta.get("cross_5_20"),
                "volume_ratio": ta.get("volume_ratio"),
            })
        except Exception as e:
            logger.debug("[스크리너] TA 계산 실패 (%s): %s", code, e)
        if (i + 1) % 50 == 0:
            logger.info("[스크리너] TA 진행: %d/%d", i + 1, len(codes))

    logger.info("[스크리너] TA 배치 완료: %d종목", len(results))
    return results


def compute_foreign_signals(n: int = 3000) -> list[dict]:
    """시총 상위 n개 종목의 5일 외인·기관 순매수 합계 수집.
    반환: list of {stock_code, foreign_net_buy}
    pykrx get_market_net_purchases_of_equities_by_ticker 사용 (시장별 1 call).
    """
    from datetime import datetime, timedelta, timezone
    from pykrx import stock as krx_stock
    from app.db.trade_db import get_top_market_cap_codes

    _KST = timezone(timedelta(hours=9))
    codes_set = set(get_top_market_cap_codes(n))

    today = datetime.now(_KST)
    # 주말 보정
    while today.weekday() >= 5:
        today -= timedelta(days=1)
    end_str   = today.strftime("%Y%m%d")
    start_str = (today - timedelta(days=11)).strftime("%Y%m%d")  # ~7 영업일 확보

    logger.info("[시장시그널] 외인 순매수 배치 시작 (%s~%s)", start_str, end_str)

    foreign_map: dict[str, int] = {}
    for market in ("KOSPI", "KOSDAQ"):
        for investor in ("외국인", "기관합계"):
            try:
                df = krx_stock.get_market_net_purchases_of_equities_by_ticker(
                    start_str, end_str, market, investor
                )
                if df is None or df.empty:
                    continue
                # 순매수 컬럼 탐색 (순매수거래량 or 순매수)
                net_col = next(
                    (c for c in df.columns if "순매수" in str(c) and "대금" not in str(c)),
                    None,
                )
                if net_col is None:
                    continue
                for ticker in df.index:
                    code = str(ticker).zfill(6)
                    if code not in codes_set:
                        continue
                    val = int(df.loc[ticker, net_col])
                    foreign_map[code] = foreign_map.get(code, 0) + val
            except Exception as e:
                logger.warning("[시장시그널] %s/%s 조회 실패: %s", market, investor, e)
        time.sleep(0.3)

    logger.info("[시장시그널] 외인·기관 순매수 완료: %d종목", len(foreign_map))
    return [{"stock_code": code, "foreign_net_buy": val} for code, val in foreign_map.items()]
