import os
import sys
import uuid
from pathlib import Path

import pytest

# backend 디렉토리를 sys.path에 추가
_BACKEND = Path(__file__).parent
sys.path.insert(0, str(_BACKEND))

# .env 로드 — 테스트에서 DATABASE_URL 등 사용 가능하게 (테스트 파일 import보다 먼저)
_ENV = _BACKEND / ".env"
if _ENV.exists():
    for _line in _ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip())

# 테스트가 TRUNCATE로 비우는 테이블 (init_db가 만드는 것들)
_TEST_TABLES = [
    "trades", "portfolio_snapshots", "user_profiles", "screener_snapshot",
    "saved_screener_filters", "alerts", "alert_watch", "disclosure_summary",
    "factcheck_results",
]


@pytest.fixture(scope="session")
def _test_pool():
    """세션 전체에서 단일 테스트 스키마 + 풀 재사용 (Supabase 연결 한도 보호)."""
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    import app.db.trade_db as tdb

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        pytest.skip("DATABASE_URL 미설정 — DB 통합 테스트 스킵")

    schema = f"test_{uuid.uuid4().hex[:10]}"
    with psycopg.connect(url) as c:
        c.execute(f'CREATE SCHEMA "{schema}"')

    if tdb._pool is not None:
        tdb._pool.close()
    tdb._pool = ConnectionPool(
        url, min_size=1, max_size=3,
        kwargs={"row_factory": dict_row, "options": f'-c search_path="{schema}"'},
        open=True,
    )
    tdb.init_db()

    yield tdb

    tdb._pool.close()
    tdb._pool = None
    with psycopg.connect(url) as c:
        c.execute(f'DROP SCHEMA "{schema}" CASCADE')


@pytest.fixture()
def db_schema(_test_pool):
    """각 테스트 시작 전 테이블 비우기 → 깨끗한 상태에서 시작."""
    tdb = _test_pool
    with tdb._conn() as con:
        con.execute(f"TRUNCATE {', '.join(_TEST_TABLES)} RESTART IDENTITY CASCADE")
    yield tdb
