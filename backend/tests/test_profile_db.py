import os, tempfile, pytest
os.environ.setdefault("DATABASE_URL", "")

def _make_db(tmp_path):
    import app.db.trade_db as db
    db._DB_PATH = tmp_path / "test.db"
    db.init_db()
    return db

def test_get_profile_default(tmp_path):
    db = _make_db(tmp_path)
    p = db.get_profile("alice")
    assert p["username"] == "alice"
    assert p["risk_level"] == "neutral"
    assert p["horizon"] == "mid"
    assert p["sectors"] == []
    assert p["ai_memo"] == ""

def test_upsert_profile(tmp_path):
    db = _make_db(tmp_path)
    db.upsert_profile("alice", risk_level="aggressive", horizon="short", sectors=["반도체", "IT·플랫폼"])
    p = db.get_profile("alice")
    assert p["risk_level"] == "aggressive"
    assert p["sectors"] == ["반도체", "IT·플랫폼"]

def test_update_ai_memo(tmp_path):
    db = _make_db(tmp_path)
    db.update_ai_memo("alice", "모멘텀 중심 투자 선호")
    p = db.get_profile("alice")
    assert p["ai_memo"] == "모멘텀 중심 투자 선호"

def test_upsert_partial(tmp_path):
    db = _make_db(tmp_path)
    db.upsert_profile("bob", risk_level="defensive")
    db.upsert_profile("bob", horizon="long")
    p = db.get_profile("bob")
    assert p["risk_level"] == "defensive"
    assert p["horizon"] == "long"
