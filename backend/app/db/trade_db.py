"""매매일지·프로필·알림·스크리너·공시요약 영속 저장 (Supabase Postgres).

기존 SQLite(compass.db)에서 이전. 커넥션 풀(psycopg_pool) 사용.
타임스탬프는 ISO 문자열(TEXT)로 저장 — 기존 문자열 비교/슬라이싱 로직 그대로 유지.
"""
import json as _json
import os
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import settings

_KST = timedelta(hours=9)

_pool: ConnectionPool | None = None


def _db_url() -> str:
    return settings.database_url or os.environ.get("DATABASE_URL", "")


def _get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        url = _db_url()
        if not url:
            raise RuntimeError("DATABASE_URL이 설정되지 않았습니다")
        _pool = ConnectionPool(
            url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        _pool.open(wait=True, timeout=15)
    return _pool


@contextmanager
def _conn():
    with _get_pool().connection() as con:
        yield con


def _kst_now() -> str:
    return (datetime.now(timezone.utc) + _KST).strftime("%Y-%m-%dT%H:%M:%S")


_SCHEMA = [
    """CREATE TABLE IF NOT EXISTS trades (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        username    TEXT    NOT NULL,
        stock_code  TEXT    NOT NULL,
        corp_name   TEXT    NOT NULL,
        trade_type  TEXT    NOT NULL,
        quantity    INTEGER NOT NULL,
        price       INTEGER NOT NULL,
        buy_price   INTEGER,
        memo        TEXT,
        created_at  TEXT    NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(username, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS portfolio_snapshots (
        id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        username        TEXT    NOT NULL,
        snapshot_date   TEXT    NOT NULL,
        total_value     BIGINT  NOT NULL,
        total_invested  BIGINT  NOT NULL,
        created_at      TEXT    NOT NULL,
        UNIQUE(username, snapshot_date)
    )""",
    """CREATE TABLE IF NOT EXISTS user_profiles (
        username    TEXT PRIMARY KEY,
        risk_level  TEXT NOT NULL DEFAULT 'neutral',
        horizon     TEXT NOT NULL DEFAULT 'mid',
        sectors     TEXT NOT NULL DEFAULT '[]',
        goal        TEXT NOT NULL DEFAULT 'growth',
        experience  TEXT NOT NULL DEFAULT 'intermediate',
        ai_memo     TEXT NOT NULL DEFAULT '',
        updated_at  TEXT NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS screener_snapshot (
        stock_code      TEXT    PRIMARY KEY,
        corp_name       TEXT    NOT NULL,
        sector          TEXT,
        market_cap      BIGINT,
        per             DOUBLE PRECISION,
        pbr             DOUBLE PRECISION,
        momentum_20d    DOUBLE PRECISION,
        rsi             DOUBLE PRECISION,
        ma_status       TEXT,
        has_ta          INTEGER NOT NULL DEFAULT 0,
        disclosure_30d  INTEGER NOT NULL DEFAULT 0,
        volume_ratio    DOUBLE PRECISION,
        foreign_net_buy BIGINT,
        updated_at      TEXT    NOT NULL DEFAULT ''
    )""",
    """CREATE TABLE IF NOT EXISTS saved_screener_filters (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        username    TEXT    NOT NULL,
        name        TEXT    NOT NULL,
        filter_json TEXT    NOT NULL,
        created_at  TEXT    NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_saved_filters_user ON saved_screener_filters(username)",
    """CREATE TABLE IF NOT EXISTS alerts (
        id          TEXT    NOT NULL,
        username    TEXT    NOT NULL,
        type        TEXT    NOT NULL,
        stock_code  TEXT    NOT NULL,
        corp_name   TEXT    NOT NULL,
        message     TEXT    NOT NULL,
        meta        TEXT,
        created_at  TEXT    NOT NULL,
        read        INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (username, id)
    )""",
    "CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(username, read, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS alert_watch (
        seq         BIGINT GENERATED ALWAYS AS IDENTITY,
        username    TEXT    NOT NULL,
        stock_code  TEXT    NOT NULL,
        corp_name   TEXT    NOT NULL,
        PRIMARY KEY (username, stock_code)
    )""",
    """CREATE TABLE IF NOT EXISTS device_tokens (
        username    TEXT    NOT NULL,
        token       TEXT    NOT NULL,
        platform    TEXT    NOT NULL DEFAULT 'ios',
        updated_at  TEXT    NOT NULL,
        PRIMARY KEY (username, token)
    )""",
    """CREATE TABLE IF NOT EXISTS disclosure_summary (
        rcept_no    TEXT    PRIMARY KEY,
        summary     TEXT    NOT NULL,
        created_at  TEXT    DEFAULT to_char(now(), 'YYYY-MM-DD"T"HH24:MI:SS')
    )""",
    """CREATE TABLE IF NOT EXISTS factcheck_results (
        id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        upload_id   TEXT    NOT NULL,
        username    TEXT    NOT NULL DEFAULT '',
        claim       TEXT    NOT NULL,
        verdict     TEXT    NOT NULL,
        reasoning   TEXT,
        created_at  TEXT    NOT NULL
    )""",
    "CREATE INDEX IF NOT EXISTS idx_factcheck_upload ON factcheck_results(upload_id)",
]


def init_db() -> None:
    with _conn() as con:
        for ddl in _SCHEMA:
            con.execute(ddl)
        # 구버전 호환 — 컬럼 없으면 추가
        for ddl in (
            "ALTER TABLE screener_snapshot ADD COLUMN IF NOT EXISTS disclosure_30d INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE screener_snapshot ADD COLUMN IF NOT EXISTS volume_ratio DOUBLE PRECISION",
            "ALTER TABLE screener_snapshot ADD COLUMN IF NOT EXISTS foreign_net_buy BIGINT",
            "ALTER TABLE factcheck_results ADD COLUMN IF NOT EXISTS username TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS goal TEXT NOT NULL DEFAULT 'growth'",
            "ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS experience TEXT NOT NULL DEFAULT 'intermediate'",
        ):
            try:
                con.execute(ddl)
            except Exception:
                pass
        # alerts PK 마이그레이션: 단일 id → (username, id) — 사용자별 알림 유실 방지
        # 단일 컬럼 PK일 때만 1회 교정 (idempotent)
        try:
            con.execute("""
                DO $$
                DECLARE n int;
                BEGIN
                  SELECT count(*) INTO n FROM pg_index i
                    WHERE i.indrelid = 'alerts'::regclass AND i.indisprimary;
                  IF n = 1 THEN
                    SELECT array_length(i.indkey::int[], 1) INTO n FROM pg_index i
                      WHERE i.indrelid = 'alerts'::regclass AND i.indisprimary;
                    IF n = 1 THEN
                      ALTER TABLE alerts DROP CONSTRAINT alerts_pkey;
                      ALTER TABLE alerts ADD PRIMARY KEY (username, id);
                    END IF;
                  END IF;
                END $$;
            """)
        except Exception:
            pass


def record_trade(
    username: str,
    stock_code: str,
    corp_name: str,
    trade_type: str,
    quantity: int,
    price: int,
    buy_price: int | None = None,
    memo: str | None = None,
) -> int:
    with _conn() as con:
        row = con.execute(
            """INSERT INTO trades
               (username, stock_code, corp_name, trade_type, quantity, price, buy_price, memo, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id""",
            (username, stock_code, corp_name, trade_type, quantity, price, buy_price, memo, _kst_now()),
        ).fetchone()
        return row["id"] if row else 0


def get_trades(
    username: str,
    limit: int = 50,
    offset: int = 0,
    stock_code: str | None = None,
) -> tuple[list[dict], int]:
    with _conn() as con:
        if stock_code:
            rows = con.execute(
                """SELECT * FROM trades WHERE username=%s AND stock_code=%s
                   ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                (username, stock_code, limit, offset),
            ).fetchall()
            total = con.execute(
                "SELECT COUNT(*) AS c FROM trades WHERE username=%s AND stock_code=%s",
                (username, stock_code),
            ).fetchone()["c"]
        else:
            rows = con.execute(
                """SELECT * FROM trades WHERE username=%s
                   ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                (username, limit, offset),
            ).fetchall()
            total = con.execute(
                "SELECT COUNT(*) AS c FROM trades WHERE username=%s",
                (username,),
            ).fetchone()["c"]
        return [dict(r) for r in rows], total


def update_memo(username: str, trade_id: int, memo: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE trades SET memo=%s WHERE id=%s AND username=%s",
            (memo, trade_id, username),
        )
        return cur.rowcount > 0


def save_snapshot(username: str, date: str, total_value: int, total_invested: int) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO portfolio_snapshots (username, snapshot_date, total_value, total_invested, created_at)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT(username, snapshot_date) DO UPDATE SET
                   total_value=excluded.total_value,
                   total_invested=excluded.total_invested,
                   created_at=excluded.created_at""",
            (username, date, total_value, total_invested, _kst_now()),
        )


def get_snapshots(username: str, days: int = 90) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT snapshot_date, total_value, total_invested
               FROM portfolio_snapshots WHERE username=%s
               ORDER BY snapshot_date DESC LIMIT %s""",
            (username, days),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))


def delete_trade(username: str, trade_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM trades WHERE id=%s AND username=%s", (trade_id, username))
        return cur.rowcount > 0


def update_trade(
    username: str,
    trade_id: int,
    trade_type: str,
    quantity: int,
    price: int,
    buy_price: int | None,
) -> bool:
    with _conn() as con:
        cur = con.execute(
            """UPDATE trades SET trade_type=%s, quantity=%s, price=%s, buy_price=%s
               WHERE id=%s AND username=%s""",
            (trade_type, quantity, price, buy_price, trade_id, username),
        )
        return cur.rowcount > 0


def get_realized_summary(username: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT id, stock_code, corp_name, quantity, price, buy_price, created_at
               FROM trades
               WHERE username=%s AND trade_type='sell' AND buy_price IS NOT NULL
               ORDER BY created_at DESC""",
            (username,),
        ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["realized_pnl"] = (d["price"] - d["buy_price"]) * d["quantity"]
            d["date"] = d["created_at"][:10]
            result.append(d)
        return result


def get_profile(username: str) -> dict:
    """user_profiles 조회. 없으면 기본값 반환 (DB에 저장하지 않음)."""
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM user_profiles WHERE username=%s", (username,)
        ).fetchone()
    if row is None:
        return {
            "username": username,
            "risk_level": "neutral",
            "horizon": "mid",
            "sectors": [],
            "goal": "growth",
            "experience": "intermediate",
            "ai_memo": "",
            "updated_at": "",
        }
    d = dict(row)
    d["sectors"] = _json.loads(d["sectors"] or "[]")
    return d


def upsert_profile(
    username: str,
    risk_level: str | None = None,
    horizon: str | None = None,
    sectors: list[str] | None = None,
    goal: str | None = None,
    experience: str | None = None,
) -> None:
    """투자 성향 저장. None 필드는 기존 값 유지 (ai_memo는 건드리지 않음)."""
    current = get_profile(username)
    new_risk = risk_level if risk_level is not None else current["risk_level"]
    new_horizon = horizon if horizon is not None else current["horizon"]
    new_sectors = sectors if sectors is not None else current["sectors"]
    new_goal = goal if goal is not None else current.get("goal", "growth")
    new_exp = experience if experience is not None else current.get("experience", "intermediate")
    with _conn() as con:
        con.execute(
            """INSERT INTO user_profiles (username, risk_level, horizon, sectors, goal, experience, ai_memo, updated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT(username) DO UPDATE SET
                   risk_level=excluded.risk_level,
                   horizon=excluded.horizon,
                   sectors=excluded.sectors,
                   goal=excluded.goal,
                   experience=excluded.experience,
                   updated_at=excluded.updated_at""",
            (username, new_risk, new_horizon, _json.dumps(new_sectors, ensure_ascii=False),
             new_goal, new_exp, current["ai_memo"], _kst_now()),
        )


def update_ai_memo(username: str, memo: str) -> None:
    """AI 추론 메모만 업데이트. 프로필이 없으면 기본값으로 생성."""
    with _conn() as con:
        con.execute(
            """INSERT INTO user_profiles (username, risk_level, horizon, sectors, ai_memo, updated_at)
               VALUES (%s, 'neutral', 'mid', '[]', %s, %s)
               ON CONFLICT(username) DO UPDATE SET
                   ai_memo=excluded.ai_memo,
                   updated_at=excluded.updated_at""",
            (username, memo, _kst_now()),
        )


def upsert_screener_snapshot(rows: list[dict]) -> None:
    """전 종목 스냅샷 배치 upsert. disclosure_30d/volume_ratio/foreign_net_buy는 기존 값 유지."""
    if not rows:
        return
    today = _kst_now()[:10]
    payload = [{
        **r,
        "disclosure_30d":  r.get("disclosure_30d", 0),
        "volume_ratio":    r.get("volume_ratio"),
        "foreign_net_buy": r.get("foreign_net_buy"),
        "updated_at":      today,
    } for r in rows]
    with _conn() as con:
        con.cursor().executemany(
            """INSERT INTO screener_snapshot
               (stock_code, corp_name, sector, market_cap, per, pbr,
                momentum_20d, rsi, ma_status, has_ta, disclosure_30d,
                volume_ratio, foreign_net_buy, updated_at)
               VALUES (%(stock_code)s, %(corp_name)s, %(sector)s, %(market_cap)s, %(per)s, %(pbr)s,
                       %(momentum_20d)s, %(rsi)s, %(ma_status)s, %(has_ta)s, %(disclosure_30d)s,
                       %(volume_ratio)s, %(foreign_net_buy)s, %(updated_at)s)
               ON CONFLICT(stock_code) DO UPDATE SET
                 corp_name=excluded.corp_name, sector=excluded.sector,
                 market_cap=excluded.market_cap, per=excluded.per, pbr=excluded.pbr,
                 momentum_20d=excluded.momentum_20d, rsi=excluded.rsi,
                 ma_status=excluded.ma_status, has_ta=excluded.has_ta,
                 updated_at=excluded.updated_at""",
            payload,
        )


def update_market_signals(signals: list[dict]) -> None:
    """종목별 volume_ratio·foreign_net_buy 일괄 업데이트."""
    if not signals:
        return
    with _conn() as con:
        con.cursor().executemany(
            """UPDATE screener_snapshot
               SET volume_ratio=%(volume_ratio)s, foreign_net_buy=%(foreign_net_buy)s
               WHERE stock_code=%(stock_code)s""",
            signals,
        )


def update_disclosure_counts(counts: dict[str, int]) -> None:
    """종목코드별 30일 공시 건수 일괄 업데이트."""
    if not counts:
        return
    with _conn() as con:
        con.cursor().executemany(
            "UPDATE screener_snapshot SET disclosure_30d = %s WHERE stock_code = %s",
            [(cnt, code) for code, cnt in counts.items()],
        )


def query_screener(
    sector: str | None = None,
    market_cap_min: int | None = None,
    market_cap_max: int | None = None,
    per_min: float | None = None,
    per_max: float | None = None,
    pbr_max: float | None = None,
    rsi_min: float | None = None,
    rsi_max: float | None = None,
    ma_status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """조건에 맞는 종목을 has_ta DESC 정렬로 최대 limit개 반환."""
    clauses = []
    params: list = []
    if sector:
        clauses.append("sector = %s")
        params.append(sector)
    if market_cap_min is not None:
        clauses.append("market_cap >= %s")
        params.append(market_cap_min)
    if market_cap_max is not None:
        clauses.append("market_cap <= %s")
        params.append(market_cap_max)
    if per_min is not None or per_max is not None:
        clauses.append("per IS NOT NULL AND per > 0")
    if per_min is not None:
        clauses.append("per >= %s")
        params.append(per_min)
    if per_max is not None:
        clauses.append("per <= %s")
        params.append(per_max)
    if pbr_max is not None:
        clauses.append("pbr IS NOT NULL AND pbr > 0 AND pbr <= %s")
        params.append(pbr_max)
    # rsi/market_cap filters intentionally exclude NULL rows (no TA data = not yet computed)
    if rsi_min is not None:
        clauses.append("rsi >= %s")
        params.append(rsi_min)
    if rsi_max is not None:
        clauses.append("rsi <= %s")
        params.append(rsi_max)
    if ma_status:
        clauses.append("ma_status = %s")
        params.append(ma_status)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM screener_snapshot {where} ORDER BY has_ta DESC, market_cap DESC NULLS LAST LIMIT %s",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_top_market_cap_codes(n: int = 300) -> list[str]:
    """시총 상위 n개 종목코드 반환."""
    with _conn() as con:
        rows = con.execute(
            "SELECT stock_code FROM screener_snapshot ORDER BY market_cap DESC NULLS LAST LIMIT %s",
            (n,),
        ).fetchall()
    return [r["stock_code"] for r in rows]


def save_filter(username: str, name: str, filter_json: str) -> int:
    with _conn() as con:
        row = con.execute(
            "INSERT INTO saved_screener_filters (username, name, filter_json, created_at) VALUES (%s, %s, %s, %s) RETURNING id",
            (username, name, filter_json, _kst_now()),
        ).fetchone()
        return row["id"] if row else 0


def get_saved_filters(username: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM saved_screener_filters WHERE username = %s ORDER BY created_at DESC",
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_filter(filter_id: int, username: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM saved_screener_filters WHERE id = %s AND username = %s",
            (filter_id, username),
        )
        return cur.rowcount > 0


# ─── 알림 시스템 ──────────────────────────────────────────────────────────────

def insert_alert(
    username: str,
    alert_id: str,
    type_: str,
    stock_code: str,
    corp_name: str,
    message: str,
    meta: dict | None = None,
) -> bool:
    """알림 저장. 중복 alert_id는 무시(ON CONFLICT DO NOTHING).
    새로 저장된 경우에만 True를 반환하고, 그때만 APNs 푸시를 best-effort로 발송한다."""
    with _conn() as con:
        cur = con.execute(
            """INSERT INTO alerts
               (id, username, type, stock_code, corp_name, message, meta, created_at, read)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0)
               ON CONFLICT(username, id) DO NOTHING""",
            (
                alert_id, username, type_, stock_code, corp_name, message,
                _json.dumps(meta, ensure_ascii=False) if meta else None,
                _kst_now(),
            ),
        )
        inserted = cur.rowcount > 0

    if inserted:
        # 푸시는 부가 기능 — 실패해도 알림 저장에는 영향 없게 격리. (lazy import: DB층이 푸시/httpx에 하드 의존하지 않게)
        try:
            from app.push.apns import send_to_user
            send_to_user(username, title=corp_name, body=message,
                         data={"alert_id": alert_id, "type": type_, "stock_code": stock_code})
        except Exception:
            pass
    return inserted


# ─── 기기 푸시 토큰 ────────────────────────────────────────────────────────────

def upsert_device_token(username: str, token: str, platform: str = "ios") -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO device_tokens (username, token, platform, updated_at)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT(username, token) DO UPDATE SET
                 platform=excluded.platform, updated_at=excluded.updated_at""",
            (username, token, platform, _kst_now()),
        )


def get_device_tokens(username: str) -> list[str]:
    with _conn() as con:
        rows = con.execute(
            "SELECT token FROM device_tokens WHERE username=%s", (username,)
        ).fetchall()
    return [r["token"] for r in rows]


def delete_device_token(token: str) -> None:
    """무효(410/BadDeviceToken) 토큰 정리 — 토큰 기준 전체 삭제."""
    with _conn() as con:
        con.execute("DELETE FROM device_tokens WHERE token=%s", (token,))


def get_unread_alerts(username: str) -> list[dict]:
    """읽지 않은 알림 최신순 반환."""
    with _conn() as con:
        rows = con.execute(
            """SELECT id, type, stock_code, corp_name, message, meta, created_at
               FROM alerts WHERE username=%s AND read=0
               ORDER BY created_at DESC""",
            (username,),
        ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["meta"] = _json.loads(d["meta"]) if d["meta"] else None
        d["read"] = False
        result.append(d)
    return result


def mark_alerts_read(username: str, ids: list[str]) -> None:
    if not ids:
        return
    with _conn() as con:
        con.cursor().executemany(
            "UPDATE alerts SET read=1 WHERE id=%s AND username=%s",
            [(alert_id, username) for alert_id in ids],
        )


def delete_alert(username: str, alert_id: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM alerts WHERE id=%s AND username=%s",
            (alert_id, username),
        )
        return cur.rowcount > 0


def cleanup_old_alerts() -> None:
    """30일 이상 된 read=1 알림 삭제."""
    cutoff = (datetime.now(timezone.utc) + _KST - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as con:
        con.execute("DELETE FROM alerts WHERE read=1 AND created_at < %s", (cutoff,))


def get_unread_alert_counts(username: str, stock_codes: list[str]) -> dict[str, int]:
    """종목코드별 미읽은 알림 건수 (포트폴리오 뱃지용)."""
    if not stock_codes:
        return {}
    placeholders = ",".join(["%s"] * len(stock_codes))
    # placeholders contains only "%s" tokens — no user data in SQL string
    with _conn() as con:
        rows = con.execute(
            f"""SELECT stock_code, COUNT(*) as cnt
                FROM alerts WHERE username=%s AND read=0
                AND stock_code IN ({placeholders})
                GROUP BY stock_code""",
            [username, *stock_codes],
        ).fetchall()
    return {r["stock_code"]: r["cnt"] for r in rows}


def get_alert_watch(username: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT stock_code, corp_name FROM alert_watch WHERE username=%s ORDER BY seq",
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_alert_watch(username: str, stock_code: str, corp_name: str) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO alert_watch (username, stock_code, corp_name) VALUES (%s, %s, %s)
               ON CONFLICT(username, stock_code) DO NOTHING""",
            (username, stock_code, corp_name),
        )


def remove_alert_watch(username: str, stock_code: str) -> None:
    with _conn() as con:
        con.execute(
            "DELETE FROM alert_watch WHERE username=%s AND stock_code=%s",
            (username, stock_code),
        )


# ─── 공시 AI 요약 캐시 ────────────────────────────────────────────────────────

def get_disclosure_summaries(rcept_nos: list[str]) -> dict[str, str]:
    """rcept_no 리스트로 캐시된 요약 일괄 조회."""
    if not rcept_nos:
        return {}
    placeholders = ",".join(["%s"] * len(rcept_nos))
    with _conn() as con:
        rows = con.execute(
            f"SELECT rcept_no, summary FROM disclosure_summary WHERE rcept_no IN ({placeholders})",
            rcept_nos,
        ).fetchall()
    return {r["rcept_no"]: r["summary"] for r in rows}


def save_disclosure_summary(rcept_no: str, summary: str) -> None:
    if not rcept_no or not summary:
        return
    with _conn() as con:
        con.execute(
            """INSERT INTO disclosure_summary(rcept_no, summary) VALUES(%s, %s)
               ON CONFLICT(rcept_no) DO UPDATE SET summary=excluded.summary""",
            (rcept_no, summary),
        )


# ─── 팩트체크 결과 영속 ────────────────────────────────────────────────────────

def save_factcheck_results(upload_id: str, claims: list[dict], username: str) -> None:
    """본인 업로드별 팩트체크 결과 저장 (기존 결과는 교체)."""
    if not upload_id:
        return
    now = _kst_now()
    with _conn() as con:
        con.execute(
            "DELETE FROM factcheck_results WHERE upload_id=%s AND username=%s",
            (upload_id, username),
        )
        if claims:
            con.cursor().executemany(
                """INSERT INTO factcheck_results (upload_id, username, claim, verdict, reasoning, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                [(upload_id, username, c.get("claim", ""), c.get("verdict", "근거없음"),
                  c.get("reasoning", ""), now) for c in claims],
            )


def get_factcheck_results(upload_id: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT claim, verdict, reasoning, created_at FROM factcheck_results WHERE upload_id=%s ORDER BY id",
            (upload_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_verified_claims(upload_ids: list[str]) -> list[dict]:
    """여러 업로드의 '지지' 판정 주장만 반환 (채팅 답변 그라운딩용)."""
    if not upload_ids:
        return []
    placeholders = ",".join(["%s"] * len(upload_ids))
    with _conn() as con:
        rows = con.execute(
            f"""SELECT claim, verdict FROM factcheck_results
                WHERE upload_id IN ({placeholders}) AND verdict IN ('지지', '모순')
                ORDER BY id""",
            upload_ids,
        ).fetchall()
    return [dict(r) for r in rows]
