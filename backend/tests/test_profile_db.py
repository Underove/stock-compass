def test_get_profile_default(db_schema):
    db = db_schema
    db.init_db()
    p = db.get_profile("alice")
    assert p["username"] == "alice"
    assert p["risk_level"] == "neutral"
    assert p["horizon"] == "mid"
    assert p["sectors"] == []
    assert p["ai_memo"] == ""

def test_upsert_profile(db_schema):
    db = db_schema
    db.init_db()
    db.upsert_profile("alice", risk_level="aggressive", horizon="short", sectors=["반도체", "IT·플랫폼"])
    p = db.get_profile("alice")
    assert p["risk_level"] == "aggressive"
    assert p["sectors"] == ["반도체", "IT·플랫폼"]

def test_update_ai_memo(db_schema):
    db = db_schema
    db.init_db()
    db.update_ai_memo("alice", "모멘텀 중심 투자 선호")
    p = db.get_profile("alice")
    assert p["ai_memo"] == "모멘텀 중심 투자 선호"

def test_upsert_partial(db_schema):
    db = db_schema
    db.init_db()
    db.upsert_profile("bob", risk_level="defensive")
    db.upsert_profile("bob", horizon="long")
    p = db.get_profile("bob")
    assert p["risk_level"] == "defensive"
    assert p["horizon"] == "long"
