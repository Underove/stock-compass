import sqlite3
import json as _json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "compass.db"
_KST = timedelta(hours=9)


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(_DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _kst_now() -> str:
    return (datetime.now(timezone.utc) + _KST).strftime("%Y-%m-%dT%H:%M:%S")


def init_db() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS trades (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    NOT NULL,
                stock_code  TEXT    NOT NULL,
                corp_name   TEXT    NOT NULL,
                trade_type  TEXT    NOT NULL,
                quantity    INTEGER NOT NULL,
                price       INTEGER NOT NULL,
                buy_price   INTEGER,
                memo        TEXT,
                created_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_trades_user
                ON trades(username, created_at DESC);

            CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                username        TEXT    NOT NULL,
                snapshot_date   TEXT    NOT NULL,
                total_value     INTEGER NOT NULL,
                total_invested  INTEGER NOT NULL,
                created_at      TEXT    NOT NULL,
                UNIQUE(username, snapshot_date)
            );

            CREATE TABLE IF NOT EXISTS user_profiles (
                username    TEXT PRIMARY KEY,
                risk_level  TEXT NOT NULL DEFAULT 'neutral',
                horizon     TEXT NOT NULL DEFAULT 'mid',
                sectors     TEXT NOT NULL DEFAULT '[]',
                ai_memo     TEXT NOT NULL DEFAULT '',
                updated_at  TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS screener_snapshot (
                stock_code  TEXT    PRIMARY KEY,
                corp_name   TEXT    NOT NULL,
                sector      TEXT,
                market_cap  INTEGER,
                per         REAL,
                pbr         REAL,
                momentum_20d REAL,
                rsi         REAL,
                ma_status   TEXT,
                has_ta      INTEGER NOT NULL DEFAULT 0,
                updated_at  TEXT    NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS saved_screener_filters (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                username    TEXT    NOT NULL,
                name        TEXT    NOT NULL,
                filter_json TEXT    NOT NULL,
                created_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_saved_filters_user
                ON saved_screener_filters(username);
        """)


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
        cur = con.execute(
            """INSERT INTO trades
               (username, stock_code, corp_name, trade_type, quantity, price, buy_price, memo, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (username, stock_code, corp_name, trade_type, quantity, price, buy_price, memo, _kst_now()),
        )
        return cur.lastrowid or 0


def get_trades(
    username: str,
    limit: int = 50,
    offset: int = 0,
    stock_code: str | None = None,
) -> tuple[list[dict], int]:
    with _conn() as con:
        if stock_code:
            rows = con.execute(
                """SELECT * FROM trades WHERE username=? AND stock_code=?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (username, stock_code, limit, offset),
            ).fetchall()
            total = con.execute(
                "SELECT COUNT(*) FROM trades WHERE username=? AND stock_code=?",
                (username, stock_code),
            ).fetchone()[0]
        else:
            rows = con.execute(
                """SELECT * FROM trades WHERE username=?
                   ORDER BY created_at DESC LIMIT ? OFFSET ?""",
                (username, limit, offset),
            ).fetchall()
            total = con.execute(
                "SELECT COUNT(*) FROM trades WHERE username=?",
                (username,),
            ).fetchone()[0]
        return [dict(r) for r in rows], total


def update_memo(username: str, trade_id: int, memo: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE trades SET memo=? WHERE id=? AND username=?",
            (memo, trade_id, username),
        )
        return cur.rowcount > 0


def save_snapshot(username: str, date: str, total_value: int, total_invested: int) -> None:
    with _conn() as con:
        con.execute(
            """INSERT INTO portfolio_snapshots (username, snapshot_date, total_value, total_invested, created_at)
               VALUES (?, ?, ?, ?, ?)
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
               FROM portfolio_snapshots WHERE username=?
               ORDER BY snapshot_date DESC LIMIT ?""",
            (username, days),
        ).fetchall()
        return list(reversed([dict(r) for r in rows]))


def delete_trade(username: str, trade_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM trades WHERE id=? AND username=?", (trade_id, username))
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
            """UPDATE trades SET trade_type=?, quantity=?, price=?, buy_price=?
               WHERE id=? AND username=?""",
            (trade_type, quantity, price, buy_price, trade_id, username),
        )
        return cur.rowcount > 0


def get_realized_summary(username: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT id, stock_code, corp_name, quantity, price, buy_price, created_at
               FROM trades
               WHERE username=? AND trade_type='sell' AND buy_price IS NOT NULL
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
            "SELECT * FROM user_profiles WHERE username=?", (username,)
        ).fetchone()
    if row is None:
        return {
            "username": username,
            "risk_level": "neutral",
            "horizon": "mid",
            "sectors": [],
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
) -> None:
    """투자 성향 저장. None 필드는 기존 값 유지 (ai_memo는 건드리지 않음)."""
    current = get_profile(username)
    new_risk = risk_level if risk_level is not None else current["risk_level"]
    new_horizon = horizon if horizon is not None else current["horizon"]
    new_sectors = sectors if sectors is not None else current["sectors"]
    with _conn() as con:
        con.execute(
            """INSERT INTO user_profiles (username, risk_level, horizon, sectors, ai_memo, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                   risk_level=excluded.risk_level,
                   horizon=excluded.horizon,
                   sectors=excluded.sectors,
                   updated_at=excluded.updated_at""",
            (username, new_risk, new_horizon, _json.dumps(new_sectors, ensure_ascii=False),
             current["ai_memo"], _kst_now()),
        )


def update_ai_memo(username: str, memo: str) -> None:
    """AI 추론 메모만 업데이트. 프로필이 없으면 기본값으로 생성."""
    with _conn() as con:
        con.execute(
            """INSERT INTO user_profiles (username, risk_level, horizon, sectors, ai_memo, updated_at)
               VALUES (?, 'neutral', 'mid', '[]', ?, ?)
               ON CONFLICT(username) DO UPDATE SET
                   ai_memo=excluded.ai_memo,
                   updated_at=excluded.updated_at""",
            (username, memo, _kst_now()),
        )


def upsert_screener_snapshot(rows: list[dict]) -> None:
    """전 종목 스냅샷 배치 upsert. rows: list of dicts with screener_snapshot columns."""
    today = _kst_now()[:10]
    with _conn() as con:
        con.executemany(
            """INSERT OR REPLACE INTO screener_snapshot
               (stock_code, corp_name, sector, market_cap, per, pbr,
                momentum_20d, rsi, ma_status, has_ta, updated_at)
               VALUES (:stock_code, :corp_name, :sector, :market_cap, :per, :pbr,
                       :momentum_20d, :rsi, :ma_status, :has_ta, :updated_at)""",
            [{**r, "updated_at": today} for r in rows],
        )


def query_screener(
    sector: str | None = None,
    market_cap_min: int | None = None,
    market_cap_max: int | None = None,
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
        clauses.append("sector = ?")
        params.append(sector)
    if market_cap_min is not None:
        clauses.append("market_cap >= ?")
        params.append(market_cap_min)
    if market_cap_max is not None:
        clauses.append("market_cap <= ?")
        params.append(market_cap_max)
    if per_max is not None:
        clauses.append("per IS NOT NULL AND per > 0 AND per <= ?")
        params.append(per_max)
    if pbr_max is not None:
        clauses.append("pbr IS NOT NULL AND pbr > 0 AND pbr <= ?")
        params.append(pbr_max)
    # rsi/market_cap filters intentionally exclude NULL rows (no TA data = not yet computed)
    if rsi_min is not None:
        clauses.append("rsi >= ?")
        params.append(rsi_min)
    if rsi_max is not None:
        clauses.append("rsi <= ?")
        params.append(rsi_max)
    if ma_status:
        clauses.append("ma_status = ?")
        params.append(ma_status)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    with _conn() as con:
        rows = con.execute(
            f"SELECT * FROM screener_snapshot {where} ORDER BY has_ta DESC, market_cap DESC LIMIT ?",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def get_top_market_cap_codes(n: int = 300) -> list[str]:
    """시총 상위 n개 종목코드 반환."""
    with _conn() as con:
        rows = con.execute(
            "SELECT stock_code FROM screener_snapshot ORDER BY market_cap DESC LIMIT ?",
            (n,),
        ).fetchall()
    return [r["stock_code"] for r in rows]


def save_filter(username: str, name: str, filter_json: str) -> int:
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO saved_screener_filters (username, name, filter_json, created_at) VALUES (?, ?, ?, ?)",
            (username, name, filter_json, _kst_now()),
        )
        return cur.lastrowid or 0


def get_saved_filters(username: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT * FROM saved_screener_filters WHERE username = ? ORDER BY created_at DESC",
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_filter(filter_id: int, username: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM saved_screener_filters WHERE id = ? AND username = ?",
            (filter_id, username),
        )
        return cur.rowcount > 0
