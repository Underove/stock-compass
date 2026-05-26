# backend/tests/test_screener_api.py
import json
import os
os.environ.setdefault("DATABASE_URL", "")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.db.trade_db as trade_db
    trade_db._DB_PATH = tmp_path / "test.db"
    trade_db.init_db()

    # 스냅샷 seed
    trade_db.upsert_screener_snapshot([
        {"stock_code": "005930", "corp_name": "삼성전자", "sector": "반도체",
         "market_cap": 3000000, "per": 12.5, "pbr": 1.2, "momentum_20d": 3.5,
         "rsi": 28.0, "ma_status": "below", "has_ta": 1},
        {"stock_code": "000660", "corp_name": "SK하이닉스", "sector": "반도체",
         "market_cap": 800000, "per": 20.0, "pbr": 1.5, "momentum_20d": -1.2,
         "rsi": 55.0, "ma_status": "above", "has_ta": 1},
        {"stock_code": "207940", "corp_name": "삼성바이오로직스", "sector": "바이오·제약",
         "market_cap": 600000, "per": 80.0, "pbr": 8.0, "momentum_20d": 2.1,
         "rsi": 62.0, "ma_status": "golden", "has_ta": 1},
    ])

    # JWT 인증 우회 — FastAPI dependency_overrides 사용
    from app.api.auth import get_current_user
    from main import app as fastapi_app
    fastapi_app.dependency_overrides[get_current_user] = lambda: "test@example.com"

    yield TestClient(fastapi_app)

    # cleanup
    fastapi_app.dependency_overrides.pop(get_current_user, None)


def test_screener_no_filter(client):
    res = client.post("/api/screener", json={})
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 3


def test_screener_sector_filter(client):
    res = client.post("/api/screener", json={"sector": "반도체"})
    assert res.status_code == 200
    codes = [r["stock_code"] for r in res.json()]
    assert "005930" in codes
    assert "207940" not in codes


def test_screener_rsi_filter(client):
    res = client.post("/api/screener", json={"rsi_max": 30.0})
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["stock_code"] == "005930"


def test_screener_per_filter(client):
    res = client.post("/api/screener", json={"per_max": 15.0})
    assert res.status_code == 200
    codes = [r["stock_code"] for r in res.json()]
    assert "005930" in codes
    assert "000660" not in codes


def test_similar_stocks(client):
    res = client.get("/api/screener/similar/005930")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    codes = [r["stock_code"] for r in data]
    assert "005930" not in codes  # 자기 자신 제외


def test_saved_filters_lifecycle(client):
    # 저장
    res = client.post("/api/screener/filters", json={"name": "반도체 과매도", "sector": "반도체", "rsi_max": 30.0})
    assert res.status_code == 200
    fid = res.json()["id"]

    # 조회
    res = client.get("/api/screener/filters")
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert res.json()[0]["name"] == "반도체 과매도"

    # 삭제
    res = client.delete(f"/api/screener/filters/{fid}")
    assert res.status_code == 200
    assert client.get("/api/screener/filters").json() == []
