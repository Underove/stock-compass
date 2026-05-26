import sqlite3
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
