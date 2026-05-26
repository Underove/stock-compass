# Sub-project D: 알림 고도화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 목표가/손절가 알림을 SQLite DB로 전환하고, 공시·거래량·기술지표 알림을 추가하며, AlertDropdown에 모니터링 종목 관리와 개별 삭제 UI를 추가한다.

**Architecture:** `compass.db`에 `alerts`, `alert_watch` 테이블 추가. 스케줄러 job 3개 신규, 기존 job 1개 수정. FastAPI 엔드포인트 인증 추가 + 5개 신규. Next.js AlertDropdown 전면 개편.

**Tech Stack:** Python 3.12, FastAPI, SQLite3(동기), APScheduler CronTrigger(Asia/Seoul), Next.js 16, React, TypeScript

---

## 파일 구조

| 파일 | 역할 |
|------|------|
| `backend/app/db/trade_db.py` | alert/alert_watch 테이블 생성 + CRUD 9개 함수 |
| `backend/app/scheduler/jobs.py` | job_check_price_alerts 수정, 헬퍼 함수, 신규 job 3개 |
| `backend/main.py` | 신규 job 3개 스케줄러 등록 |
| `backend/app/api/notifications.py` | 인증 추가 + DELETE 알림 + watch CRUD 3개 |
| `backend/app/api/portfolio.py` | get_portfolio_alerts → DB 기반으로 교체 |
| `frontend/lib/types.ts` | Alert 타입, WatchStock 타입 추가 |
| `frontend/lib/api.ts` | PriceAlert→Alert 교체, deleteAlert, watch API 3개 |
| `frontend/app/page.tsx` | AlertBell/AlertDropdown 전면 개편 |

---

## Task 1: DB — alert 테이블 + CRUD 함수

**Files:**
- Modify: `backend/app/db/trade_db.py:20-93`

- [ ] **Step 1: `init_db()` executescript에 alert 테이블 2개 추가**

`trade_db.py`의 `init_db()` 함수 안 `con.executescript(...)` 문자열 끝(`;`)에 다음 DDL 추가:

```python
            CREATE TABLE IF NOT EXISTS alerts (
                id          TEXT    PRIMARY KEY,
                username    TEXT    NOT NULL,
                type        TEXT    NOT NULL,
                stock_code  TEXT    NOT NULL,
                corp_name   TEXT    NOT NULL,
                message     TEXT    NOT NULL,
                meta        TEXT,
                created_at  TEXT    NOT NULL,
                read        INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_alerts_user
                ON alerts(username, read, created_at DESC);

            CREATE TABLE IF NOT EXISTS alert_watch (
                username    TEXT    NOT NULL,
                stock_code  TEXT    NOT NULL,
                corp_name   TEXT    NOT NULL,
                PRIMARY KEY (username, stock_code)
            );
```

- [ ] **Step 2: CRUD 함수 9개 추가 — `trade_db.py` 파일 끝에 append**

```python
# ─── 알림 시스템 ──────────────────────────────────────────────────────────────

def insert_alert(
    username: str,
    alert_id: str,
    type_: str,
    stock_code: str,
    corp_name: str,
    message: str,
    meta: dict | None = None,
) -> None:
    """중복 alert_id는 무시 (INSERT OR IGNORE)."""
    with _conn() as con:
        con.execute(
            """INSERT OR IGNORE INTO alerts
               (id, username, type, stock_code, corp_name, message, meta, created_at, read)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                alert_id, username, type_, stock_code, corp_name, message,
                _json.dumps(meta, ensure_ascii=False) if meta else None,
                _kst_now(),
            ),
        )


def get_unread_alerts(username: str) -> list[dict]:
    """읽지 않은 알림 최신순 반환."""
    with _conn() as con:
        rows = con.execute(
            """SELECT id, type, stock_code, corp_name, message, meta, created_at
               FROM alerts WHERE username=? AND read=0
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
    with _conn() as con:
        con.executemany(
            "UPDATE alerts SET read=1 WHERE id=? AND username=?",
            [(alert_id, username) for alert_id in ids],
        )


def delete_alert(username: str, alert_id: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "DELETE FROM alerts WHERE id=? AND username=?",
            (alert_id, username),
        )
        return cur.rowcount > 0


def cleanup_old_alerts() -> None:
    """30일 이상 된 read=1 알림 삭제."""
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) + timedelta(hours=9) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as con:
        con.execute("DELETE FROM alerts WHERE read=1 AND created_at < ?", (cutoff,))


def get_unread_alert_counts(username: str, stock_codes: list[str]) -> dict[str, int]:
    """종목코드별 미읽은 알림 건수 (포트폴리오 뱃지용)."""
    if not stock_codes:
        return {}
    placeholders = ",".join("?" * len(stock_codes))
    with _conn() as con:
        rows = con.execute(
            f"""SELECT stock_code, COUNT(*) as cnt
                FROM alerts WHERE username=? AND read=0
                AND stock_code IN ({placeholders})
                GROUP BY stock_code""",
            [username, *stock_codes],
        ).fetchall()
    return {r["stock_code"]: r["cnt"] for r in rows}


def get_alert_watch(username: str) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            "SELECT stock_code, corp_name FROM alert_watch WHERE username=? ORDER BY rowid",
            (username,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_alert_watch(username: str, stock_code: str, corp_name: str) -> None:
    with _conn() as con:
        con.execute(
            "INSERT OR IGNORE INTO alert_watch (username, stock_code, corp_name) VALUES (?, ?, ?)",
            (username, stock_code, corp_name),
        )


def remove_alert_watch(username: str, stock_code: str) -> None:
    with _conn() as con:
        con.execute(
            "DELETE FROM alert_watch WHERE username=? AND stock_code=?",
            (username, stock_code),
        )
```

- [ ] **Step 3: import 검증**

```bash
cd ~/Desktop/stock-compass/backend && source venv/bin/activate
python -c "from app.db.trade_db import insert_alert, get_unread_alerts, mark_alerts_read, delete_alert, cleanup_old_alerts, get_unread_alert_counts, get_alert_watch, add_alert_watch, remove_alert_watch; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: DB에 테이블 생성 확인**

```bash
python -c "
from app.db.trade_db import init_db
import sqlite3
from pathlib import Path
init_db()
db = Path('data/compass.db')
con = sqlite3.connect(db)
tables = [r[0] for r in con.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print(tables)
assert 'alerts' in tables
assert 'alert_watch' in tables
print('Tables OK')
"
```
Expected: `alerts`와 `alert_watch`가 목록에 포함

- [ ] **Step 5: Commit**

```bash
git add backend/app/db/trade_db.py
git commit -m "feat(db): alerts + alert_watch 테이블 및 CRUD 함수 추가"
```

---

## Task 2: Scheduler — 헬퍼 함수 + job_check_price_alerts 수정

**Files:**
- Modify: `backend/app/scheduler/jobs.py`

- [ ] **Step 1: 파일 상단 imports에 trade_db import 추가**

`jobs.py` 파일 상단 (현재 `import datetime`, `import json`, ... 이후) 에 추가:

```python
from app.db.trade_db import (
    insert_alert,
    get_unread_alerts as _db_get_unread,
    mark_alerts_read as _db_mark_read,
    get_alert_watch,
    get_unread_alert_counts,
)
```

- [ ] **Step 2: `_load_alerts()`, `_save_alerts()`, `get_unread_alerts()`, `mark_alerts_read()` 함수 제거 후 헬퍼 추가**

기존 `# ─── 알림 시스템` 섹션(line 60~84)을 다음으로 교체:

```python
# ─── 알림 시스템 ──────────────────────────────────────────────────────────────

def get_unread_alerts(username: str) -> list[dict]:
    return _db_get_unread(username)


def mark_alerts_read(username: str, ids: list[str]) -> None:
    _db_mark_read(username, ids)


def _get_all_usernames() -> list[str]:
    """포트폴리오/관심종목 JSON 파일 + alert_watch DB에서 전체 username 수집."""
    seen: set[str] = set()
    for f in DATA_DIR.glob("portfolio_*.json"):
        seen.add(f.stem[len("portfolio_"):])
    for f in DATA_DIR.glob("watchlist_*.json"):
        seen.add(f.stem[len("watchlist_"):])
    try:
        from app.db.trade_db import _conn
        with _conn() as con:
            for row in con.execute("SELECT DISTINCT username FROM alert_watch").fetchall():
                seen.add(row[0])
    except Exception:
        pass
    return list(seen)


def _load_portfolio_json(username: str) -> list[dict]:
    f = DATA_DIR / f"portfolio_{username}.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _load_watchlist_json(username: str) -> list[dict]:
    f = DATA_DIR / f"watchlist_{username}.json"
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return []


def _get_monitored_stocks(username: str) -> list[dict]:
    """포트폴리오 + 관심종목 + alert_watch 합집합 (중복 제거)."""
    seen: set[str] = set()
    result: list[dict] = []
    for src in (
        _load_portfolio_json(username),
        _load_watchlist_json(username),
        get_alert_watch(username),
    ):
        for item in src:
            code = item["stock_code"]
            if code not in seen:
                seen.add(code)
                result.append({"stock_code": code, "corp_name": item["corp_name"]})
    return result
```

- [ ] **Step 3: `job_check_price_alerts()` 수정**

기존 함수 전체를 다음으로 교체:

```python
def job_check_price_alerts() -> None:
    """목표가·손절가 도달 체크 (장 중 매 5분). DB 기반."""
    now = _now_kst()
    if now.weekday() >= 5:
        return
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60 or minutes > 15 * 60 + 30:
        return

    logger.info("[스케줄러] 가격 알림 체크")
    try:
        from app.collectors.krx import get_current_price
        date_str = now.strftime("%Y-%m-%d")
        for username in _get_all_usernames():
            for item in _load_portfolio_json(username):
                if not item.get("target_price") and not item.get("stop_loss"):
                    continue
                try:
                    price_data = get_current_price(item["stock_code"])
                    cp = price_data["current_price"]

                    if item.get("target_price") and cp >= item["target_price"]:
                        alert_id = f"{item['stock_code']}_target_{date_str}"
                        insert_alert(
                            username, alert_id, "target",
                            item["stock_code"], item["corp_name"],
                            f"{item['corp_name']} 목표가 {item['target_price']:,}원 도달 (현재 {cp:,}원)",
                            {"current_price": cp, "trigger_price": item["target_price"]},
                        )

                    if item.get("stop_loss") and cp <= item["stop_loss"]:
                        alert_id = f"{item['stock_code']}_stoploss_{date_str}"
                        insert_alert(
                            username, alert_id, "stop_loss",
                            item["stock_code"], item["corp_name"],
                            f"{item['corp_name']} 손절가 {item['stop_loss']:,}원 도달 (현재 {cp:,}원)",
                            {"current_price": cp, "trigger_price": item["stop_loss"]},
                        )
                except Exception as e:
                    logger.warning("[스케줄러] %s 가격 조회 실패: %s", item["stock_code"], e)
    except Exception as e:
        logger.error("[스케줄러] 알림 체크 실패: %s", e)
```

- [ ] **Step 4: import 검증**

```bash
python -c "from app.scheduler.jobs import job_check_price_alerts, _get_all_usernames, _get_monitored_stocks; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/scheduler/jobs.py
git commit -m "feat(scheduler): job_check_price_alerts DB 전환, 헬퍼 함수 추가"
```

---

## Task 3: Scheduler — job_check_dart_alerts

**Files:**
- Modify: `backend/app/scheduler/jobs.py`

- [ ] **Step 1: `job_check_dart_alerts()` 함수 추가** (파일 끝, `job_check_price_alerts` 아래)

```python
def job_check_dart_alerts() -> None:
    """보유/관심/모니터링 종목 신규 공시 체크 (평일 16:40 KST)."""
    import time
    now = _now_kst()
    if now.weekday() >= 5:
        return
    logger.info("[스케줄러] 공시 알림 체크")
    try:
        from app.collectors.dart import download_corp_codes, fetch_recent_disclosures
        today_str = now.strftime("%Y%m%d")
        corp_list = download_corp_codes()
        stock_to_corp = {c["stock_code"]: c["corp_code"] for c in corp_list}

        # 전체 유저 × 모니터링 종목 수집 → 종목별 대상 유저 매핑
        stock_users: dict[str, list[str]] = {}  # stock_code → [username, ...]
        for username in _get_all_usernames():
            for item in _get_monitored_stocks(username):
                stock_users.setdefault(item["stock_code"], []).append(username)

        for stock_code, usernames in stock_users.items():
            corp_code = stock_to_corp.get(stock_code)
            if not corp_code:
                continue
            try:
                disclosures = fetch_recent_disclosures(corp_code, days=1, max_count=10)
                for d in disclosures:
                    if d.get("rcept_dt", "") != today_str:
                        continue
                    rcept_no = d.get("rcept_no", "")
                    alert_id = f"{stock_code}_dart_{rcept_no}"
                    report_nm = d.get("report_nm", "공시")
                    corp_name = d.get("corp_name", stock_code)
                    message = f"{corp_name} 신규 공시: {report_nm}"
                    meta = {"rcept_no": rcept_no, "report_nm": report_nm, "rcept_dt": d.get("rcept_dt", "")}
                    for username in usernames:
                        insert_alert(username, alert_id, "dart", stock_code, corp_name, message, meta)
            except Exception as e:
                logger.warning("[스케줄러] 공시 조회 실패 (%s): %s", stock_code, e)
            time.sleep(0.3)
        logger.info("[스케줄러] 공시 알림 체크 완료")
    except Exception as e:
        logger.error("[스케줄러] 공시 알림 체크 실패: %s", e)
```

- [ ] **Step 2: import 검증**

```bash
python -c "from app.scheduler.jobs import job_check_dart_alerts; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/scheduler/jobs.py
git commit -m "feat(scheduler): job_check_dart_alerts 공시 알림 추가"
```

---

## Task 4: Scheduler — volume + technical jobs + cleanup

**Files:**
- Modify: `backend/app/scheduler/jobs.py`

- [ ] **Step 1: `job_check_volume_alerts()` 추가**

```python
def job_check_volume_alerts() -> None:
    """거래량 급등 알림 (평일 16:45 KST, volume_ratio >= 2.0)."""
    now = _now_kst()
    if now.weekday() >= 5:
        return
    logger.info("[스케줄러] 거래량 알림 체크")
    try:
        from app.db.trade_db import _conn
        date_str = now.strftime("%Y-%m-%d")

        # screener_snapshot에서 volume_ratio 조회
        with _conn() as con:
            snap_rows = con.execute(
                "SELECT stock_code, corp_name, volume_ratio FROM screener_snapshot WHERE volume_ratio IS NOT NULL"
            ).fetchall()
        snap = {r["stock_code"]: {"corp_name": r["corp_name"], "volume_ratio": r["volume_ratio"]} for r in snap_rows}

        for username in _get_all_usernames():
            for item in _get_monitored_stocks(username):
                code = item["stock_code"]
                row = snap.get(code)
                vol_ratio: float | None = None

                if row:
                    vol_ratio = row["volume_ratio"]
                else:
                    # 폴백: ta_engine 직접 계산
                    try:
                        from app.collectors.ta_engine import analyze as ta_analyze
                        ta = ta_analyze(code)
                        vol_ratio = ta.get("volume_ratio")
                    except Exception:
                        pass

                if vol_ratio is not None and vol_ratio >= 2.0:
                    alert_id = f"{code}_volume_{date_str}"
                    corp_name = (row or {}).get("corp_name", item["corp_name"])
                    insert_alert(
                        username, alert_id, "volume_spike", code, corp_name,
                        f"{corp_name} 거래량 급등 (평균 대비 {vol_ratio:.1f}배)",
                        {"volume_ratio": round(vol_ratio, 2)},
                    )
        logger.info("[스케줄러] 거래량 알림 체크 완료")
    except Exception as e:
        logger.error("[스케줄러] 거래량 알림 체크 실패: %s", e)
```

- [ ] **Step 2: `job_check_technical_alerts()` 추가**

```python
def job_check_technical_alerts() -> None:
    """RSI/MA 크로스 기술지표 알림 (평일 16:50 KST)."""
    now = _now_kst()
    if now.weekday() >= 5:
        return
    logger.info("[스케줄러] 기술지표 알림 체크")
    try:
        from app.db.trade_db import _conn
        date_str = now.strftime("%Y-%m-%d")

        with _conn() as con:
            snap_rows = con.execute(
                "SELECT stock_code, corp_name, rsi, ma_status FROM screener_snapshot WHERE has_ta=1"
            ).fetchall()
        snap = {
            r["stock_code"]: {"corp_name": r["corp_name"], "rsi": r["rsi"], "ma_status": r["ma_status"]}
            for r in snap_rows
        }

        for username in _get_all_usernames():
            for item in _get_monitored_stocks(username):
                code = item["stock_code"]
                row = snap.get(code)
                rsi: float | None = None
                ma_status: str | None = None

                if row:
                    rsi = row["rsi"]
                    ma_status = row["ma_status"]
                else:
                    try:
                        from app.collectors.ta_engine import analyze as ta_analyze
                        ta = ta_analyze(code)
                        rsi = ta.get("rsi")
                        ma_status = ta.get("cross_5_20")
                    except Exception:
                        pass

                corp_name = (row or {}).get("corp_name", item["corp_name"])

                if rsi is not None and rsi >= 70:
                    insert_alert(
                        username, f"{code}_rsi_overbought_{date_str}", "rsi_overbought",
                        code, corp_name,
                        f"{corp_name} RSI 과매수 진입 (RSI {rsi:.1f})",
                        {"rsi": round(rsi, 1)},
                    )
                if rsi is not None and rsi <= 30:
                    insert_alert(
                        username, f"{code}_rsi_oversold_{date_str}", "rsi_oversold",
                        code, corp_name,
                        f"{corp_name} RSI 과매도 진입 (RSI {rsi:.1f})",
                        {"rsi": round(rsi, 1)},
                    )
                if ma_status == "golden":
                    insert_alert(
                        username, f"{code}_golden_cross_{date_str}", "golden_cross",
                        code, corp_name,
                        f"{corp_name} 골든크로스 발생 (5MA↑20MA)",
                        None,
                    )
                if ma_status == "dead":
                    insert_alert(
                        username, f"{code}_dead_cross_{date_str}", "dead_cross",
                        code, corp_name,
                        f"{corp_name} 데드크로스 발생 (5MA↓20MA)",
                        None,
                    )
        logger.info("[스케줄러] 기술지표 알림 체크 완료")
    except Exception as e:
        logger.error("[스케줄러] 기술지표 알림 체크 실패: %s", e)
```

- [ ] **Step 3: `job_refresh_screener_ta()` 끝에 cleanup 호출 추가**

`jobs.py`에서 `job_refresh_screener_ta` 함수를 찾아 마지막 `logger.info(...)` 뒤에 추가:

```python
    # 오래된 알림 정리
    try:
        from app.db.trade_db import cleanup_old_alerts
        cleanup_old_alerts()
    except Exception as e:
        logger.warning("[스케줄러] 알림 정리 실패: %s", e)
```

- [ ] **Step 4: import 검증**

```bash
python -c "from app.scheduler.jobs import job_check_volume_alerts, job_check_technical_alerts; print('OK')"
```
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/scheduler/jobs.py
git commit -m "feat(scheduler): volume/technical alert jobs + cleanup 추가"
```

---

## Task 5: main.py — 신규 job 스케줄러 등록

**Files:**
- Modify: `backend/main.py:29-38` (import 섹션), `backend/main.py:50-64` (scheduler.add_job 섹션)

- [ ] **Step 1: import에 신규 job 3개 추가**

```python
from app.scheduler.jobs import (  # noqa: E402
    job_check_price_alerts,
    job_check_dart_alerts,
    job_check_volume_alerts,
    job_check_technical_alerts,
    job_generate_briefing,
    job_premarket_news_summary,
    job_save_portfolio_snapshots,
    job_refresh_screener_fundamentals,
    job_refresh_screener_ta,
    job_refresh_screener_market_signals,
    job_refresh_disclosure_counts,
)
```

- [ ] **Step 2: lifespan 안 스케줄러에 job 3개 추가**

기존 `scheduler.add_job(job_refresh_disclosure_counts, ...)` 뒤에:

```python
    # 공시 알림 (평일 16:40 KST)
    scheduler.add_job(job_check_dart_alerts, CronTrigger(day_of_week="mon-fri", hour=16, minute=40, timezone=KST))
    # 거래량 급등 알림 (평일 16:45 KST)
    scheduler.add_job(job_check_volume_alerts, CronTrigger(day_of_week="mon-fri", hour=16, minute=45, timezone=KST))
    # 기술지표 알림 (평일 16:50 KST)
    scheduler.add_job(job_check_technical_alerts, CronTrigger(day_of_week="mon-fri", hour=16, minute=50, timezone=KST))
```

- [ ] **Step 3: logging 메시지 업데이트**

```python
    logging.getLogger(__name__).info(
        "스케줄러 시작 — 브리핑 15:35 / 알림 5분 / 뉴스 08:50 / 스냅샷 15:32 / "
        "스크리너 16:10·16:20·16:35 / 공시 18:30 / 알림고도화 16:40·16:45·16:50"
    )
```

- [ ] **Step 4: 서버 시작 검증**

```bash
python -c "
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
# main.py import 검증만
import main
print('main.py import OK')
"
```
Expected: `main.py import OK`

- [ ] **Step 5: Commit**

```bash
git add backend/main.py
git commit -m "feat(main): alert 고도화 job 3개 스케줄러 등록"
```

---

## Task 6: API — notifications.py 전면 개편

**Files:**
- Modify: `backend/app/api/notifications.py`

- [ ] **Step 1: 파일 전체 교체**

```python
"""알림·캐시 브리핑·뉴스 요약 API."""
import json as _json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.db.trade_db import (
    get_unread_alerts,
    mark_alerts_read,
    delete_alert,
    get_alert_watch,
    add_alert_watch,
    remove_alert_watch,
)
from app.scheduler.jobs import load_briefing_cache, load_news_cache, save_briefing_cache

router = APIRouter()


# ─── 알림 ─────────────────────────────────────────────────────────────────────

@router.get("/notifications/alerts")
def get_alerts(username: str = Depends(get_current_user)):
    """읽지 않은 알림 목록 반환 (유저별)."""
    return {"alerts": get_unread_alerts(username)}


class ReadRequest(BaseModel):
    ids: list[str]


@router.post("/notifications/alerts/read")
def mark_read(body: ReadRequest, username: str = Depends(get_current_user)):
    mark_alerts_read(username, body.ids)
    return {"ok": True}


@router.delete("/notifications/alerts/{alert_id}")
def remove_alert(alert_id: str, username: str = Depends(get_current_user)):
    """개별 알림 삭제."""
    deleted = delete_alert(username, alert_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")
    return {"ok": True}


# ─── 모니터링 종목 ────────────────────────────────────────────────────────────

class WatchItem(BaseModel):
    stock_code: str
    corp_name: str


@router.get("/notifications/watch")
def list_watch(username: str = Depends(get_current_user)):
    return {"items": get_alert_watch(username)}


@router.post("/notifications/watch")
def add_watch(item: WatchItem, username: str = Depends(get_current_user)):
    add_alert_watch(username, item.stock_code, item.corp_name)
    return {"ok": True}


@router.delete("/notifications/watch/{stock_code}")
def remove_watch(stock_code: str, username: str = Depends(get_current_user)):
    remove_alert_watch(username, stock_code)
    return {"ok": True}


# ─── 캐시된 브리핑 ────────────────────────────────────────────────────────────

@router.get("/notifications/briefing-cache")
def get_briefing_cache():
    cached = load_briefing_cache()
    return {"cached": cached}


# ─── 개장 전 뉴스 요약 ────────────────────────────────────────────────────────

@router.get("/notifications/premarket-news")
def get_premarket_news():
    cached = load_news_cache()
    return {"cached": cached}


@router.post("/notifications/premarket-news/generate")
def generate_premarket_news():
    from app.scheduler.jobs import job_premarket_news_summary
    job_premarket_news_summary()
    return {"cached": load_news_cache()}


@router.post("/notifications/briefing/generate")
def generate_briefing_now():
    from app.api.portfolio import get_portfolio_briefing
    result = get_portfolio_briefing()
    save_briefing_cache(result)
    return {"cached": result}
```

- [ ] **Step 2: import 검증**

```bash
python -c "from app.api.notifications import router; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/notifications.py
git commit -m "feat(api): notifications 인증 추가, 개별 삭제, watch CRUD 엔드포인트"
```

---

## Task 7: API — portfolio/alerts DB 전환

**Files:**
- Modify: `backend/app/api/portfolio.py:566-593`

- [ ] **Step 1: `get_portfolio_alerts()` 함수 교체**

기존 함수(line 566-593) 전체를:

```python
@router.get("/portfolio/alerts")
def get_portfolio_alerts(username: str = Depends(get_current_user)):
    """포트폴리오 종목별 미읽은 알림 건수 (배지용)."""
    items = _load(username)
    if not items:
        return {"alerts": {}}
    stock_codes = [item["stock_code"] for item in items]
    from app.db.trade_db import get_unread_alert_counts
    counts = get_unread_alert_counts(username, stock_codes)
    # 알림 없는 종목도 0으로 포함
    return {"alerts": {code: counts.get(code, 0) for code in stock_codes}}
```

- [ ] **Step 2: import 검증**

```bash
python -c "from app.api.portfolio import get_portfolio_alerts; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/portfolio.py
git commit -m "feat(api): portfolio/alerts DART 직접 조회 → DB 알림 카운트로 교체"
```

---

## Task 8: Frontend — types.ts + api.ts

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: `types.ts`에 Alert, WatchStock 타입 추가**

`frontend/lib/types.ts` 파일 끝에 추가:

```typescript
// ─── 알림 고도화 ──────────────────────────────────────────────────────────────

export type AlertType =
  | "target"
  | "stop_loss"
  | "dart"
  | "volume_spike"
  | "rsi_overbought"
  | "rsi_oversold"
  | "golden_cross"
  | "dead_cross";

export type Alert = {
  id: string;
  type: AlertType;
  stock_code: string;
  corp_name: string;
  message: string;
  meta: Record<string, unknown> | null;
  created_at: string;
  read: boolean;
};

export type WatchStock = {
  stock_code: string;
  corp_name: string;
};
```

- [ ] **Step 2: `api.ts` — `PriceAlert` 타입 제거 후 교체, 함수 5개 추가**

`api.ts`에서 다음을 찾아 교체:

찾을 코드 (line 253-262):
```typescript
export type PriceAlert = {
  id: string;
  type: "target" | "stop_loss";
  stock_code: string;
  corp_name: string;
  current_price: number;
  trigger_price: number;
  message: string;
  created_at: string;
  read: boolean;
};
```

교체할 코드:
```typescript
export type { Alert as PriceAlert } from "./types";  // 하위 호환
import type { Alert, WatchStock } from "./types";
```

그리고 기존 `fetchAlerts`, `markAlertsRead` 함수(line 279-286)를 교체:

```typescript
export async function fetchAlerts(): Promise<Alert[]> {
  const data = await getJSON<{ alerts: Alert[] }>("/api/notifications/alerts");
  return data.alerts;
}

export async function markAlertsRead(ids: string[]): Promise<void> {
  await postJSON("/api/notifications/alerts/read", { ids });
}

export async function deleteAlert(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/notifications/alerts/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
}

export async function fetchAlertWatch(): Promise<WatchStock[]> {
  const data = await getJSON<{ items: WatchStock[] }>("/api/notifications/watch");
  return data.items;
}

export async function addAlertWatch(stock_code: string, corp_name: string): Promise<void> {
  await postJSON("/api/notifications/watch", { stock_code, corp_name });
}

export async function removeAlertWatch(stock_code: string): Promise<void> {
  await fetch(`${API_BASE}/api/notifications/watch/${encodeURIComponent(stock_code)}`, {
    method: "DELETE",
    headers: await authHeaders(),
  });
}
```

- [ ] **Step 3: `authHeaders()` 함수 확인**

```bash
grep -n "authHeaders\|async function auth" frontend/lib/api.ts | head -5
```

`authHeaders()` 함수가 있는지 확인. 없으면 `getJSON` 함수 내부에서 헤더 처리하는 방식으로 `deleteAlert`/`removeAlertWatch` 재작성:

```typescript
export async function deleteAlert(id: string): Promise<void> {
  const token = await getToken();
  await fetch(`${API_BASE}/api/notifications/alerts/${encodeURIComponent(id)}`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}

export async function removeAlertWatch(stock_code: string): Promise<void> {
  const token = await getToken();
  await fetch(`${API_BASE}/api/notifications/watch/${encodeURIComponent(stock_code)}`, {
    method: "DELETE",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
}
```

- [ ] **Step 4: TypeScript 타입 검증**

```bash
cd ~/Desktop/stock-compass/frontend && npx tsc --noEmit 2>&1 | head -30
```
Expected: 오류 없음

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(frontend): Alert 타입 교체, watch/deleteAlert API 함수 추가"
```

---

## Task 9: Frontend — AlertBell + AlertDropdown 개편

**Files:**
- Modify: `frontend/app/page.tsx`

- [ ] **Step 1: import 추가**

`page.tsx` 상단 import 줄에서 `fetchAlerts, markAlertsRead` 뒤에 추가:

```typescript
import { fetchAlerts, fetchAlertWatch, markAlertsRead, deleteAlert, addAlertWatch, removeAlertWatch, initAuth, fetchMarketIndices, searchStock } from "../lib/api";
import type { Alert, WatchStock } from "../lib/types";
```

그리고 기존 `PriceAlert` 참조를 `Alert`로 교체 (2곳):
- `useState<PriceAlert[]>([])` → `useState<Alert[]>([])`
- `alerts: PriceAlert[]` (AlertBell, AlertDropdown prop types)

- [ ] **Step 2: `watchStocks` state + `loadWatch` effect 추가**

`page.tsx`의 `const [alerts, setAlerts] = useState<Alert[]>([]);` 바로 뒤에:

```typescript
const [watchStocks, setWatchStocks] = useState<WatchStock[]>([]);

async function loadWatch() {
  try { setWatchStocks(await fetchAlertWatch()); } catch {}
}

useEffect(() => {
  loadWatch();
}, []);
```

- [ ] **Step 3: AlertBell props 업데이트**

```typescript
function AlertBell({ alerts, show, onToggle }: {
  alerts: Alert[];
  show: boolean;
  onToggle: () => void;
})
```

내부 로직은 동일 유지 (unread count 표시).

- [ ] **Step 4: AlertDropdown 전면 교체**

기존 `AlertDropdown` 함수 전체를 다음으로 교체:

```typescript
function AlertDropdown({ alerts, watchStocks, onClose, onReadAll, onDelete, onAddWatch, onRemoveWatch }: {
  alerts: Alert[];
  watchStocks: WatchStock[];
  onClose: () => void;
  onReadAll: () => void;
  onDelete: (id: string) => void;
  onAddWatch: (stock_code: string, corp_name: string) => void;
  onRemoveWatch: (stock_code: string) => void;
}) {
  const [watchQuery, setWatchQuery] = useState("");
  const [watchResults, setWatchResults] = useState<{ stock_code: string; corp_name: string }[]>([]);
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!watchQuery.trim()) { setWatchResults([]); return; }
    const t = setTimeout(async () => {
      setSearching(true);
      try { setWatchResults((await searchStock(watchQuery)).slice(0, 4)); }
      catch { setWatchResults([]); }
      finally { setSearching(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [watchQuery]);

  const ALERT_COLOR: Record<string, string> = {
    dart: "var(--primary)",
    volume_spike: "var(--orange)",
    rsi_overbought: "#BF5AF2",
    rsi_oversold: "#BF5AF2",
    golden_cross: "#BF5AF2",
    dead_cross: "#BF5AF2",
    target: "var(--green)",
    stop_loss: "var(--red)",
  };
  const ALERT_LABEL: Record<string, string> = {
    dart: "공시",
    volume_spike: "거래량",
    rsi_overbought: "RSI 과매수",
    rsi_oversold: "RSI 과매도",
    golden_cross: "골든크로스",
    dead_cross: "데드크로스",
    target: "목표가",
    stop_loss: "손절가",
  };

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 19 }} />
      <div style={{
        position: "fixed", top: 56, right: 12, zIndex: 20,
        background: "var(--surface)", borderRadius: 16,
        boxShadow: "var(--shadow-lg)", width: 340,
        overflow: "hidden", border: "0.5px solid var(--sep)",
        maxHeight: "80dvh", display: "flex", flexDirection: "column",
      }}>
        {/* 헤더 */}
        <div style={{ padding: "13px 16px 11px", borderBottom: "0.5px solid var(--sep)", display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
          <span style={{ fontSize: 14, fontWeight: 700 }}>알림 {alerts.length}건</span>
          <button onClick={onReadAll} style={{ fontSize: 12, color: "var(--primary)", fontWeight: 600 }}>모두 읽음</button>
        </div>

        {/* 모니터링 종목 */}
        <div style={{ padding: "10px 16px 8px", borderBottom: "0.5px solid var(--sep)", flexShrink: 0 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--label3)", marginBottom: 6 }}>모니터링 종목</div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 6 }}>
            {watchStocks.map(w => (
              <div key={w.stock_code} style={{
                display: "flex", alignItems: "center", gap: 4,
                background: "var(--surface2)", borderRadius: 8,
                padding: "3px 8px", fontSize: 12, fontWeight: 600, color: "var(--label)",
              }}>
                {w.corp_name}
                <button onClick={() => onRemoveWatch(w.stock_code)} style={{ fontSize: 11, color: "var(--label3)", padding: 0, lineHeight: 1 }}>×</button>
              </div>
            ))}
          </div>
          <div style={{ position: "relative" }}>
            <input
              value={watchQuery}
              onChange={e => setWatchQuery(e.target.value)}
              placeholder="+ 종목 추가"
              style={{
                width: "100%", padding: "6px 10px", borderRadius: 8,
                border: "0.5px solid var(--sep)", background: "var(--surface2)",
                fontSize: 12, color: "var(--label)",
              }}
            />
            {watchResults.length > 0 && (
              <div style={{
                position: "absolute", top: "calc(100% + 4px)", left: 0, right: 0, zIndex: 10,
                background: "var(--surface)", borderRadius: 10,
                boxShadow: "var(--shadow-md)", border: "0.5px solid var(--sep)",
                overflow: "hidden",
              }}>
                {watchResults.map(r => (
                  <button key={r.stock_code} onClick={() => {
                    onAddWatch(r.stock_code, r.corp_name);
                    setWatchQuery("");
                    setWatchResults([]);
                  }} style={{
                    width: "100%", padding: "8px 12px", textAlign: "left",
                    fontSize: 13, color: "var(--label)", borderBottom: "0.5px solid var(--sep)",
                  }}>
                    <span style={{ fontWeight: 700 }}>{r.corp_name}</span>
                    <span style={{ fontSize: 11, color: "var(--label3)", marginLeft: 6 }}>{r.stock_code}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 알림 목록 */}
        <div style={{ overflowY: "auto", flex: 1 }}>
          {alerts.length === 0 && (
            <div style={{ padding: "24px 16px", textAlign: "center", color: "var(--label3)", fontSize: 13 }}>새 알림 없음</div>
          )}
          {alerts.map((a, i) => {
            const color = ALERT_COLOR[a.type] ?? "var(--label2)";
            const label = ALERT_LABEL[a.type] ?? a.type;
            return (
              <div key={a.id}>
                {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 16 }} />}
                <div style={{ padding: "10px 12px 10px 16px", display: "flex", gap: 10, alignItems: "flex-start" }}>
                  <div style={{ width: 8, height: 8, borderRadius: "50%", marginTop: 5, flexShrink: 0, background: color }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color, marginBottom: 2 }}>{label}</div>
                    <div style={{ fontSize: 13, color: "var(--label)", lineHeight: 1.4 }}>{a.message}</div>
                    <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 3 }}>
                      {new Date(a.created_at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                    </div>
                  </div>
                  <button
                    onClick={() => onDelete(a.id)}
                    style={{ fontSize: 14, color: "var(--label3)", padding: "2px 4px", flexShrink: 0, lineHeight: 1 }}
                    aria-label="알림 삭제"
                  >×</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 5: AlertDropdown 호출부 업데이트**

`page.tsx`에서 `<AlertDropdown` 컴포넌트를 찾아:

```typescript
{showAlerts && alerts.length > 0 && (
  <AlertDropdown
    alerts={alerts}
    watchStocks={watchStocks}
    onClose={() => setShowAlerts(false)}
    onReadAll={async () => {
      const ids = alerts.map(a => a.id);
      await markAlertsRead(ids);
      setAlerts([]);
      setShowAlerts(false);
    }}
    onDelete={async (id) => {
      await deleteAlert(id);
      setAlerts(prev => prev.filter(a => a.id !== id));
    }}
    onAddWatch={async (stock_code, corp_name) => {
      await addAlertWatch(stock_code, corp_name);
      setWatchStocks(prev => prev.some(w => w.stock_code === stock_code) ? prev : [...prev, { stock_code, corp_name }]);
    }}
    onRemoveWatch={async (stock_code) => {
      await removeAlertWatch(stock_code);
      setWatchStocks(prev => prev.filter(w => w.stock_code !== stock_code));
    }}
  />
)}
```

그리고 `showAlerts && alerts.length > 0` 조건에서 `alerts.length > 0` 제거 (알림 없어도 드롭다운 열려야 종목 추가 가능):

```typescript
{showAlerts && (
  <AlertDropdown ... />
)}
```

- [ ] **Step 6: TypeScript 검증**

```bash
cd ~/Desktop/stock-compass/frontend && npx tsc --noEmit 2>&1 | head -20
```
Expected: 오류 없음

- [ ] **Step 7: dev 서버에서 브라우저 확인**

```bash
# 서버가 실행 중인지 확인
curl -s http://localhost:3000 | head -5
```

브라우저에서 http://localhost:3000 접속 후:
- 헤더 알림 벨 클릭 → 드롭다운 열림 확인
- "모니터링 종목" 섹션에 검색창 보임
- 알림 행 오른쪽에 × 버튼 보임
- 알림 없을 때도 드롭다운 열림 확인

- [ ] **Step 8: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "feat(frontend): AlertDropdown 개편 — 타입 교체, watch 관리, 개별 삭제"
```

---

## 최종 검증

- [ ] **백엔드 전체 import**

```bash
cd ~/Desktop/stock-compass/backend && source venv/bin/activate
python -c "
import app.api.portfolio, app.api.notifications, app.scheduler.jobs
from app.db.trade_db import insert_alert, get_unread_alerts, delete_alert, cleanup_old_alerts, get_alert_watch
print('Backend OK')
"
```
Expected: `Backend OK`

- [ ] **프론트엔드 타입 검증**

```bash
cd ~/Desktop/stock-compass/frontend && npx tsc --noEmit
```
Expected: 출력 없음 (오류 0개)

- [ ] **최종 커밋**

```bash
cd ~/Desktop/stock-compass
git log --oneline -8
```
