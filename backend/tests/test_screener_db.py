# backend/tests/test_screener_db.py

def test_upsert_and_query_screener(db_schema):
    db = db_schema
    db.init_db()
    db.upsert_screener_snapshot([
        {"stock_code": "005930", "corp_name": "삼성전자", "sector": "반도체",
         "market_cap": 3000000, "per": 12.5, "pbr": 1.2, "momentum_20d": 3.5,
         "rsi": None, "ma_status": None, "has_ta": 0},
        {"stock_code": "000660", "corp_name": "SK하이닉스", "sector": "반도체",
         "market_cap": 800000, "per": 8.0, "pbr": 1.5, "momentum_20d": -1.2,
         "rsi": 42.0, "ma_status": "above", "has_ta": 1},
    ])
    results = db.query_screener(sector="반도체", per_max=15.0)
    assert len(results) == 2
    assert results[0]["stock_code"] == "000660"  # has_ta=1 → first by has_ta DESC sort

def test_query_screener_rsi_filter(db_schema):
    db = db_schema
    db.init_db()
    db.upsert_screener_snapshot([
        {"stock_code": "005930", "corp_name": "삼성전자", "sector": "반도체",
         "market_cap": 3000000, "per": 12.5, "pbr": 1.2, "momentum_20d": 3.5,
         "rsi": 25.0, "ma_status": "below", "has_ta": 1},
        {"stock_code": "000660", "corp_name": "SK하이닉스", "sector": "반도체",
         "market_cap": 800000, "per": 8.0, "pbr": 1.5, "momentum_20d": -1.2,
         "rsi": 55.0, "ma_status": "above", "has_ta": 1},
    ])
    results = db.query_screener(rsi_max=30.0)
    assert len(results) == 1
    assert results[0]["stock_code"] == "005930"

def test_saved_filters_crud(db_schema):
    db = db_schema
    db.init_db()
    fid = db.save_filter("alice", "반도체 과매도", '{"sector": "반도체", "rsi_max": 30}')
    filters = db.get_saved_filters("alice")
    assert len(filters) == 1
    assert filters[0]["name"] == "반도체 과매도"
    db.delete_filter(fid, "alice")
    assert db.get_saved_filters("alice") == []

def test_get_top_market_cap_codes(db_schema):
    db = db_schema
    db.init_db()
    rows = [
        {"stock_code": f"{i:06d}", "corp_name": f"종목{i}", "sector": "기타",
         "market_cap": i * 1000, "per": None, "pbr": None, "momentum_20d": 0.0,
         "rsi": None, "ma_status": None, "has_ta": 0}
        for i in range(1, 400)
    ]
    db.upsert_screener_snapshot(rows)
    codes = db.get_top_market_cap_codes(300)
    assert len(codes) == 300
    assert codes[0] == "000399"  # market_cap=399000 → 최대
