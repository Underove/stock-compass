"""DB·네트워크 불필요한 순수 로직 테스트 (빠르고 안정적)."""
from app.collectors.kis_ws import parse_index
from app.rag.factcheck import compute_signal
from app.llm.gemini import parse_json_response


# ─── KIS WS 지수 파싱 (60만 버그 지점) ────────────────────────────────────────

def _index_frame(tr_id: str, fields: list[str]) -> str:
    return f"0|{tr_id}|001|{'^'.join(fields)}"


def test_parse_index_kospi_up():
    # [0]업종코드 [1]시간 [2]현재가 [3]부호(2=상승) [4]전일대비 [5]등락률 [6]거래량
    raw = _index_frame("H0UPCNT0", ["0001", "100000", "2650.50", "2", "30.25", "1.15", "500000"])
    r = parse_index(raw)
    assert r is not None
    assert r["stock_code"] == "KOSPI"
    assert r["current_price"] == 2650.5
    assert r["change_pct"] == 1.15
    assert r["change_amount"] == 30.25


def test_parse_index_kosdaq_down():
    # 부호 5 = 하락 → 음수
    raw = _index_frame("H0UPDNT0", ["1001", "100000", "850.10", "5", "12.40", "1.44", "300000"])
    r = parse_index(raw)
    assert r is not None
    assert r["stock_code"] == "KOSDAQ"
    assert r["change_pct"] == -1.44
    assert r["change_amount"] == -12.40


def test_parse_index_rejects_non_index_frame():
    assert parse_index("0|H0STCNT0|005930|...") is None  # 종목 체결, 지수 아님
    assert parse_index("garbage") is None
    assert parse_index("0|H0UPCNT0|001|onlyonefield") is None  # 필드 부족


# ─── 팩트체크 신호 산출 ────────────────────────────────────────────────────────

def test_compute_signal_all_supported():
    verdicts = [{"verdict": "지지"}, {"verdict": "지지"}, {"verdict": "지지"}]
    signal, score = compute_signal(verdicts)
    assert signal == "green"
    assert score == 100


def test_compute_signal_contradicted_lowers():
    verdicts = [{"verdict": "모순"}, {"verdict": "모순"}]
    signal, score = compute_signal(verdicts)
    assert signal == "red"
    assert score < 40


def test_compute_signal_empty():
    signal, score = compute_signal([])
    assert signal == "yellow"
    assert score == 50


def test_compute_signal_mixed():
    verdicts = [{"verdict": "지지"}, {"verdict": "근거없음"}, {"verdict": "모순"}]
    signal, score = compute_signal(verdicts)
    assert 0 <= score <= 100
    assert signal in ("green", "yellow", "red")


# ─── LLM JSON 응답 파싱 ────────────────────────────────────────────────────────

def test_parse_json_plain():
    assert parse_json_response('{"a": 1}', default={}) == {"a": 1}


def test_parse_json_codeblock():
    assert parse_json_response('```json\n{"a": 1}\n```', default={}) == {"a": 1}


def test_parse_json_embedded():
    assert parse_json_response('설명\n{"a": 1}\n끝', default={}) == {"a": 1}


def test_parse_json_invalid_returns_default():
    assert parse_json_response("not json at all", default={"fallback": True}) == {"fallback": True}
