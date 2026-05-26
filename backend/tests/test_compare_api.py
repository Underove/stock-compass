"""GET /api/compare 엔드포인트 테스트."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.db.trade_db as trade_db
    trade_db._DB_PATH = tmp_path / "test.db"
    trade_db.init_db()

    trade_db.upsert_screener_snapshot([
        {
            "stock_code": "005930", "corp_name": "삼성전자", "sector": "전기·전자",
            "market_cap": 2980000, "per": 19.2, "pbr": 1.3,
            "momentum_20d": -2.1, "rsi": 48.3, "ma_status": "below", "has_ta": 1,
            "volume_ratio": 0.9, "foreign_net_buy": -124000000000, "disclosure_30d": 0,
        },
        {
            "stock_code": "000660", "corp_name": "SK하이닉스", "sector": "전기·전자",
            "market_cap": 1120000, "per": 12.4, "pbr": 1.8,
            "momentum_20d": 8.4, "rsi": 62.1, "ma_status": "golden", "has_ta": 1,
            "volume_ratio": 2.3, "foreign_net_buy": 382000000000, "disclosure_30d": 0,
        },
    ])

    # pykrx 네트워크 호출 차단 — _get_price_series 직접 대체
    import app.api.compare as compare_mod
    monkeypatch.setattr(
        compare_mod, "_get_price_series",
        lambda code, start, end: [
            {"date": "2026-03-01", "close": 58400, "return_pct": 0.0},
            {"date": "2026-03-04", "close": 57900, "return_pct": -0.86},
        ],
    )

    from main import app
    return TestClient(app)


def test_compare_basic(client):
    r = client.get("/api/compare?codes=005930,000660&period=3m")
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "3m"
    assert len(body["stocks"]) == 2
    codes = {s["stock_code"] for s in body["stocks"]}
    assert codes == {"005930", "000660"}


def test_compare_metrics(client):
    r = client.get("/api/compare?codes=005930,000660")
    body = r.json()
    samsung = next(s for s in body["stocks"] if s["stock_code"] == "005930")
    assert samsung["corp_name"] == "삼성전자"
    assert samsung["metrics"]["per"] == pytest.approx(19.2)
    assert samsung["metrics"]["volume_ratio"] == pytest.approx(0.9)
    assert samsung["price_series"][0]["return_pct"] == pytest.approx(0.0)


def test_compare_requires_two_codes(client):
    assert client.get("/api/compare?codes=005930").status_code == 400
    assert client.get("/api/compare?codes=005930,000660,207940").status_code == 400


def test_compare_missing_stock_returns_null_metrics(client):
    """screener_snapshot에 없는 종목은 corp_name·metrics 모두 null."""
    r = client.get("/api/compare?codes=005930,999999")
    assert r.status_code == 200
    body = r.json()
    unknown = next(s for s in body["stocks"] if s["stock_code"] == "999999")
    assert unknown["corp_name"] is None
    assert unknown["metrics"]["per"] is None
    assert unknown["metrics"]["market_cap"] is None


def test_compare_invalid_period(client):
    r = client.get("/api/compare?codes=005930,000660&period=invalid")
    assert r.status_code == 400
