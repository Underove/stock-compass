# 매매일지 + 수익률 히스토리 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 포트폴리오 거래를 자동 기록하고, 총 평가액 변화·실현 손익을 SVG 그래프로 시각화하는 매매일지 탭을 PortfolioCard에 추가한다.

**Architecture:** SQLite(`backend/data/compass.db`) 2테이블 구조. portfolio.py 거래 엔드포인트에 `record_trade()` 호출 삽입. 스케줄러가 매일 15:30 KST 포트폴리오 스냅샷 저장. 프론트엔드는 TradeJournal + TradeDetailModal 컴포넌트 신규 작성, PortfolioCard에 "일지" 탭 추가.

**Tech Stack:** Python sqlite3 (표준 라이브러리), FastAPI, Next.js 15, TypeScript, SVG 직접 구현

---

## 파일 구조

| 파일 | 역할 |
|---|---|
| `backend/app/db/trade_db.py` | SQLite 초기화·거래 CRUD·스냅샷 UPSERT (신규) |
| `backend/app/api/trades.py` | /api/trades 엔드포인트 4개 (신규) |
| `backend/app/api/portfolio.py` | 매수/매도/삭제 후 record_trade() 호출 추가 |
| `backend/app/scheduler/jobs.py` | 15:30 스냅샷 job 추가 |
| `backend/main.py` | init_db() 호출 + trades 라우터 등록 |
| `frontend/lib/types.ts` | Trade, TradeSummaryItem, PortfolioSnapshot 타입 추가 |
| `frontend/lib/api.ts` | fetchTrades, updateTradeMemo, fetchTradeSummary, fetchPortfolioSnapshots 추가 |
| `frontend/components/TradeJournal.tsx` | 그래프 + 이력 리스트 (신규) |
| `frontend/components/TradeDetailModal.tsx` | 거래 상세 + 메모 편집 모달 (신규) |
| `frontend/components/PortfolioCard.tsx` | "일지" 탭 추가 |

---

## Task 0: 체크포인트 커밋

**Files:**
- 없음 (git only)

- [ ] **Step 1: 체크포인트 커밋 생성**

```bash
cd /Users/underove/Desktop/stock-compass
git add -A
git commit -m "chore: checkpoint before trade journal implementation"
```

- [ ] **Step 2: 체크포인트 해시 기록**

```bash
git log --oneline -3
```

Expected output 예시:
```
abc1234 chore: checkpoint before trade journal implementation
d8a67b5 fix: improve tab bar visibility in dark mode, relocate market status badge
...
```

롤백이 필요하면:
```bash
git reset --hard abc1234   # 위 해시로 교체
rm -f backend/data/compass.db
```

---

## Task 1: SQLite 레이어 — trade_db.py

**Files:**
- Create: `backend/app/db/trade_db.py`

- [ ] **Step 1: trade_db.py 작성**

```python
"""SQLite 기반 거래 이력 + 포트폴리오 스냅샷 저장소."""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "compass.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

KST = timezone(timedelta(hours=9))


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(str(_DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def init_db() -> None:
    """앱 시작 시 테이블 생성. 이미 존재하면 스킵."""
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
) -> None:
    """거래 1건 INSERT."""
    now = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as con:
        con.execute(
            "INSERT INTO trades "
            "(username, stock_code, corp_name, trade_type, quantity, price, buy_price, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (username, stock_code, corp_name, trade_type, quantity, price, buy_price, now),
        )


def get_trades(
    username: str,
    limit: int = 50,
    offset: int = 0,
    stock_code: str | None = None,
) -> tuple[list[dict], int]:
    """거래 이력 페이지네이션 조회. (rows, total) 반환."""
    with _conn() as con:
        if stock_code:
            rows = con.execute(
                "SELECT * FROM trades WHERE username=? AND stock_code=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (username, stock_code, limit, offset),
            ).fetchall()
            total = con.execute(
                "SELECT COUNT(*) FROM trades WHERE username=? AND stock_code=?",
                (username, stock_code),
            ).fetchone()[0]
        else:
            rows = con.execute(
                "SELECT * FROM trades WHERE username=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (username, limit, offset),
            ).fetchall()
            total = con.execute(
                "SELECT COUNT(*) FROM trades WHERE username=?",
                (username,),
            ).fetchone()[0]
    return [dict(r) for r in rows], total


def update_memo(username: str, trade_id: int, memo: str) -> bool:
    """메모 수정. 본인 소유 확인 후 UPDATE. 성공 시 True."""
    with _conn() as con:
        cur = con.execute(
            "UPDATE trades SET memo=? WHERE id=? AND username=?",
            (memo, trade_id, username),
        )
    return cur.rowcount > 0


def save_snapshot(
    username: str,
    date: str,
    total_value: int,
    total_invested: int,
) -> None:
    """날짜별 스냅샷 UPSERT (같은 날 두 번 저장하면 덮어씀)."""
    now = datetime.now(KST).strftime("%Y-%m-%dT%H:%M:%S")
    with _conn() as con:
        con.execute(
            "INSERT INTO portfolio_snapshots "
            "(username, snapshot_date, total_value, total_invested, created_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(username, snapshot_date) DO UPDATE SET "
            "total_value=excluded.total_value, total_invested=excluded.total_invested, "
            "created_at=excluded.created_at",
            (username, date, total_value, total_invested, now),
        )


def get_snapshots(username: str, days: int = 90) -> list[dict]:
    """최근 N일 스냅샷 조회 (오래된 순)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT snapshot_date, total_value, total_invested FROM portfolio_snapshots "
            "WHERE username=? ORDER BY snapshot_date ASC LIMIT ?",
            (username, days),
        ).fetchall()
    return [dict(r) for r in rows]


def get_realized_summary(username: str) -> list[dict]:
    """sell 거래 기반 실현 손익 목록 (오래된 순)."""
    with _conn() as con:
        rows = con.execute(
            "SELECT id, stock_code, corp_name, quantity, price, buy_price, created_at "
            "FROM trades WHERE username=? AND trade_type='sell' "
            "ORDER BY created_at ASC",
            (username,),
        ).fetchall()
    result = []
    for r in rows:
        r = dict(r)
        bp = r.get("buy_price") or 0
        pnl = (r["price"] - bp) * r["quantity"]
        result.append({
            "trade_id": r["id"],
            "date": r["created_at"][:10],
            "corp_name": r["corp_name"],
            "stock_code": r["stock_code"],
            "quantity": r["quantity"],
            "sell_price": r["price"],
            "buy_price": bp,
            "realized_pnl": pnl,
        })
    return result
```

- [ ] **Step 2: import 검증**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "from app.db.trade_db import init_db, record_trade, get_trades, update_memo, save_snapshot, get_snapshots, get_realized_summary; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: 기능 동작 확인**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "
from app.db.trade_db import init_db, record_trade, get_trades, save_snapshot, get_snapshots, get_realized_summary
init_db()
record_trade('test@test.com', '005930', '삼성전자', 'buy', 10, 70000)
record_trade('test@test.com', '005930', '삼성전자', 'sell', 5, 75000, buy_price=70000)
trades, total = get_trades('test@test.com')
print('거래 수:', total)
save_snapshot('test@test.com', '2026-05-26', 1000000, 900000)
snaps = get_snapshots('test@test.com')
print('스냅샷 수:', len(snaps))
summary = get_realized_summary('test@test.com')
print('실현손익:', summary[0]['realized_pnl'])
"
```

Expected:
```
거래 수: 2
스냅샷 수: 1
실현손익: 25000
```

- [ ] **Step 4: 테스트용 데이터 삭제 후 커밋**

```bash
rm -f /Users/underove/Desktop/stock-compass/backend/data/compass.db
cd /Users/underove/Desktop/stock-compass
git add backend/app/db/trade_db.py
git commit -m "feat: add SQLite trade_db layer (trades + portfolio_snapshots)"
```

---

## Task 2: 거래 API — trades.py

**Files:**
- Create: `backend/app/api/trades.py`

- [ ] **Step 1: trades.py 작성**

```python
"""매매일지 + 포트폴리오 스냅샷 API."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth import get_current_user
from app.db.trade_db import get_realized_summary, get_snapshots, get_trades, update_memo

router = APIRouter()


class MemoBody(BaseModel):
    memo: str


@router.get("/trades")
def list_trades(
    limit: int = 50,
    offset: int = 0,
    stock_code: str | None = None,
    username: str = Depends(get_current_user),
):
    trades, total = get_trades(username, limit=limit, offset=offset, stock_code=stock_code)
    return {"trades": trades, "total": total}


@router.post("/trades/{trade_id}/memo")
def set_memo(
    trade_id: int,
    body: MemoBody,
    username: str = Depends(get_current_user),
):
    ok = update_memo(username, trade_id, body.memo)
    if not ok:
        raise HTTPException(status_code=404, detail="거래를 찾을 수 없습니다")
    return {"ok": True}


@router.get("/trades/summary")
def trade_summary(username: str = Depends(get_current_user)):
    return {"items": get_realized_summary(username)}


@router.get("/portfolio/snapshots")
def portfolio_snapshots(
    days: int = 90,
    username: str = Depends(get_current_user),
):
    return {"snapshots": get_snapshots(username, days=days)}
```

- [ ] **Step 2: import 검증**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "from app.api.trades import router; print('routes:', [r.path for r in router.routes])"
```

Expected:
```
routes: ['/trades', '/trades/{trade_id}/memo', '/trades/summary', '/portfolio/snapshots']
```

- [ ] **Step 3: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add backend/app/api/trades.py
git commit -m "feat: add trades API endpoints (list, memo, summary, snapshots)"
```

---

## Task 3: main.py — init_db + 라우터 등록

**Files:**
- Modify: `backend/main.py`

- [ ] **Step 1: main.py 수정**

`from app.config import settings` 바로 아래에 추가:
```python
from app.api import trades as trades_api  # noqa: E402
from app.db.trade_db import init_db  # noqa: E402
```

`lifespan` 함수 안 `scheduler.start()` 바로 위에 추가:
```python
    init_db()
```

`app.include_router(notifications_api.router, ...)` 다음 줄에 추가:
```python
app.include_router(trades_api.router, prefix="/api", tags=["trades"])
```

수정 후 전체 lifespan 함수:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler = BackgroundScheduler(timezone=KST)
    scheduler.add_job(job_generate_briefing, CronTrigger(day_of_week="mon-fri", hour=15, minute=35, timezone=KST))
    scheduler.add_job(job_check_price_alerts, CronTrigger(day_of_week="mon-fri", hour="9-15", minute="*/5", timezone=KST))
    scheduler.add_job(job_premarket_news_summary, CronTrigger(day_of_week="mon-fri", hour=8, minute=50, timezone=KST))
    scheduler.start()
    logging.getLogger(__name__).info("스케줄러 시작 — 브리핑 15:35 / 알림 5분 / 뉴스 08:50")
    yield
    scheduler.shutdown(wait=False)
```

- [ ] **Step 2: 서버 기동 확인**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "
import app.main as m
print('라우터 등록 확인:', [r.path for r in m.app.routes if hasattr(r, 'path') and 'trade' in r.path])
"
```

Expected (순서 무관):
```
라우터 등록 확인: ['/api/trades', '/api/trades/{trade_id}/memo', '/api/trades/summary', '/api/portfolio/snapshots']
```

- [ ] **Step 3: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add backend/main.py
git commit -m "feat: register trades router and call init_db on startup"
```

---

## Task 4: portfolio.py — 거래 자동 기록

**Files:**
- Modify: `backend/app/api/portfolio.py`

- [ ] **Step 1: import 추가**

파일 상단 `from app.config import settings` 아래에 추가:
```python
from app.db.trade_db import record_trade
```

- [ ] **Step 2: add_portfolio 엔드포인트에 record_trade 추가**

기존 `add_portfolio` 함수의 `return {"ok": True, "item": item.model_dump()}` 바로 위에 추가:
```python
    record_trade(
        username=username,
        stock_code=item.stock_code,
        corp_name=item.corp_name,
        trade_type="buy",
        quantity=item.quantity,
        price=item.buy_price,
    )
```

수정 후 전체 함수:
```python
@router.post("/portfolio")
def add_portfolio(item: PortfolioItem, username: str = Depends(get_current_user)):
    items = _load(username)
    existing = next((i for i in items if i["stock_code"] == item.stock_code), None)
    if existing:
        existing.update(item.model_dump())
    else:
        items.append(item.model_dump())
    _save(items, username)
    record_trade(
        username=username,
        stock_code=item.stock_code,
        corp_name=item.corp_name,
        trade_type="buy",
        quantity=item.quantity,
        price=item.buy_price,
    )
    return {"ok": True, "item": item.model_dump()}
```

- [ ] **Step 3: remove_portfolio 엔드포인트에 record_trade 추가**

기존 `remove_portfolio` 함수를 다음으로 교체:
```python
@router.delete("/portfolio/{stock_code}")
def remove_portfolio(stock_code: str, username: str = Depends(get_current_user)):
    items = _load(username)
    target = next((i for i in items if i["stock_code"] == stock_code), None)
    _save([i for i in items if i["stock_code"] != stock_code], username)
    if target:
        record_trade(
            username=username,
            stock_code=stock_code,
            corp_name=target.get("corp_name", stock_code),
            trade_type="sell",
            quantity=target.get("quantity", 0),
            price=target.get("buy_price", 0),
            buy_price=target.get("buy_price"),
        )
    return {"ok": True}
```

- [ ] **Step 4: update_portfolio 엔드포인트에 record_trade 추가**

기존 `update_portfolio` 함수를 다음으로 교체:
```python
@router.put("/portfolio/{stock_code}")
def update_portfolio(stock_code: str, body: UpdatePortfolioBody, username: str = Depends(get_current_user)):
    items = _load(username)
    target = next((i for i in items if i["stock_code"] == stock_code), None)
    if not target:
        raise HTTPException(status_code=404, detail="종목 없음")

    old_qty = target["quantity"]
    old_buy_price = target["buy_price"]

    if body.quantity <= 0:
        items = [i for i in items if i["stock_code"] != stock_code]
        record_trade(
            username=username,
            stock_code=stock_code,
            corp_name=target.get("corp_name", stock_code),
            trade_type="sell",
            quantity=old_qty,
            price=body.buy_price,
            buy_price=old_buy_price,
        )
    else:
        qty_diff = body.quantity - old_qty
        trade_type = "buy" if qty_diff > 0 else "sell" if qty_diff < 0 else "edit"
        target["buy_price"] = body.buy_price
        target["quantity"] = body.quantity
        target["target_price"] = body.target_price
        target["stop_loss"] = body.stop_loss
        record_trade(
            username=username,
            stock_code=stock_code,
            corp_name=target.get("corp_name", stock_code),
            trade_type=trade_type,
            quantity=abs(qty_diff) if qty_diff != 0 else body.quantity,
            price=body.buy_price,
            buy_price=old_buy_price if trade_type == "sell" else None,
        )
    _save(items, username)
    return {"ok": True}
```

- [ ] **Step 5: import 검증**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "from app.api.portfolio import add_portfolio, remove_portfolio, update_portfolio; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add backend/app/api/portfolio.py
git commit -m "feat: auto-record trades on portfolio add/update/delete"
```

---

## Task 5: 스케줄러 — 일별 포트폴리오 스냅샷

**Files:**
- Modify: `backend/app/scheduler/jobs.py`

- [ ] **Step 1: job_snapshot_portfolio 함수 추가**

파일 맨 끝에 추가:
```python

# ─── 포트폴리오 스냅샷 ───────────────────────────────────────────────────────

def job_snapshot_portfolio() -> None:
    """장 마감 후 포트폴리오 총 평가액 스냅샷 저장 (평일 15:32 KST)."""
    logger.info("[스케줄러] 포트폴리오 스냅샷 저장 시작")
    from app.api.portfolio import _load, _get_price
    from app.db.trade_db import save_snapshot

    now = _now_kst()
    today = now.strftime("%Y-%m-%d")

    for portfolio_file in DATA_DIR.glob("portfolio_*.json"):
        # 파일명에서 username 추출: portfolio_user@email.com.json → user@email.com
        username = portfolio_file.stem.replace("portfolio_", "", 1)
        try:
            items = _load(username)
            if not items:
                continue

            total_value = 0
            total_invested = 0
            for item in items:
                invested = item["buy_price"] * item["quantity"]
                total_invested += invested
                try:
                    price_data = _get_price(item["stock_code"])
                    total_value += price_data["current_price"] * item["quantity"]
                except Exception:
                    total_value += invested  # 조회 실패 시 원금으로 대체

            save_snapshot(username, today, int(total_value), int(total_invested))
            logger.info("[스케줄러] %s 스냅샷 저장 완료: %d원", username, total_value)
        except Exception as e:
            logger.error("[스케줄러] %s 스냅샷 실패: %s", username, e)
```

- [ ] **Step 2: main.py에 스케줄 등록**

`backend/main.py`의 imports에 추가:
```python
from app.scheduler.jobs import (  # noqa: E402
    job_check_price_alerts,
    job_generate_briefing,
    job_premarket_news_summary,
    job_snapshot_portfolio,
)
```

`lifespan` 안 `scheduler.start()` 바로 위에 추가:
```python
    scheduler.add_job(job_snapshot_portfolio, CronTrigger(day_of_week="mon-fri", hour=15, minute=32, timezone=KST))
```

로그 메시지도 수정:
```python
    logging.getLogger(__name__).info("스케줄러 시작 — 브리핑 15:35 / 스냅샷 15:32 / 알림 5분 / 뉴스 08:50")
```

- [ ] **Step 3: import 검증**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "from app.scheduler.jobs import job_snapshot_portfolio; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add backend/app/scheduler/jobs.py backend/main.py
git commit -m "feat: add daily portfolio snapshot scheduler job at 15:32 KST"
```

---

## Task 6: 프론트엔드 타입 + API 함수

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: types.ts 타입 3개 추가**

`frontend/lib/types.ts` 파일 맨 끝에 추가:
```typescript
// ─── 매매일지 ─────────────────────────────────────────────────────────────────

export type Trade = {
  id: number;
  stock_code: string;
  corp_name: string;
  trade_type: "buy" | "sell" | "edit";
  quantity: number;
  price: number;
  buy_price: number | null;
  memo: string | null;
  created_at: string;
};

export type TradeSummaryItem = {
  trade_id: number;
  date: string;
  corp_name: string;
  stock_code: string;
  quantity: number;
  sell_price: number;
  buy_price: number;
  realized_pnl: number;
};

export type PortfolioSnapshot = {
  snapshot_date: string;
  total_value: number;
  total_invested: number;
};
```

- [ ] **Step 2: api.ts — import 타입 3개 추가 + 함수 4개 추가**

`frontend/lib/api.ts` 상단 import에 3개 추가:
```typescript
import type {
  // ... 기존 타입들 ...
  PortfolioSnapshot,
  Trade,
  TradeSummaryItem,
} from "./types";
```

파일 맨 끝에 함수 4개 추가:
```typescript
// ─── 매매일지 API ─────────────────────────────────────────────────────────────

export async function fetchTrades(params?: {
  limit?: number;
  offset?: number;
  stock_code?: string;
}): Promise<{ trades: Trade[]; total: number }> {
  const q = new URLSearchParams();
  if (params?.limit !== undefined) q.set("limit", String(params.limit));
  if (params?.offset !== undefined) q.set("offset", String(params.offset));
  if (params?.stock_code) q.set("stock_code", params.stock_code);
  return getJSON(`/api/trades?${q}`);
}

export async function updateTradeMemo(
  tradeId: number,
  memo: string,
): Promise<void> {
  await postJSON(`/api/trades/${tradeId}/memo`, { memo });
}

export async function fetchTradeSummary(): Promise<{
  items: TradeSummaryItem[];
}> {
  return getJSON("/api/trades/summary");
}

export async function fetchPortfolioSnapshots(
  days = 90,
): Promise<{ snapshots: PortfolioSnapshot[] }> {
  return getJSON(`/api/portfolio/snapshots?days=${days}`);
}
```

- [ ] **Step 3: TypeScript 검증**

```bash
cd /Users/underove/Desktop/stock-compass/frontend
npx tsc --noEmit 2>&1
```

Expected: 출력 없음 (0 errors)

- [ ] **Step 4: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat: add Trade/TradeSummaryItem/PortfolioSnapshot types and API functions"
```

---

## Task 7: TradeDetailModal 컴포넌트

**Files:**
- Create: `frontend/components/TradeDetailModal.tsx`

- [ ] **Step 1: TradeDetailModal.tsx 작성**

```typescript
"use client";

import { useState } from "react";
import { updateTradeMemo } from "../lib/api";
import type { Trade } from "../lib/types";

const TRADE_LABEL: Record<string, { text: string; color: string; bg: string }> = {
  buy:  { text: "매수", color: "var(--primary)", bg: "rgba(0,122,255,0.10)" },
  sell: { text: "매도", color: "var(--red)",     bg: "rgba(255,59,48,0.10)" },
  edit: { text: "수정", color: "var(--label3)",  bg: "var(--surface2)" },
};

function fmt(n: number) {
  return n.toLocaleString("ko-KR");
}

function formatDate(iso: string) {
  return iso.replace("T", " ").slice(0, 16);
}

export function TradeDetailModal({
  trade,
  currentPrice,
  onClose,
  onMemoSaved,
}: {
  trade: Trade;
  currentPrice?: number;
  onClose: () => void;
  onMemoSaved: (id: number, memo: string) => void;
}) {
  const [memo, setMemo] = useState(trade.memo ?? "");
  const [saving, setSaving] = useState(false);
  const label = TRADE_LABEL[trade.trade_type] ?? TRADE_LABEL.edit;
  const totalAmt = trade.price * trade.quantity;

  const pnl =
    trade.trade_type === "sell" && trade.buy_price
      ? (trade.price - trade.buy_price) * trade.quantity
      : currentPrice
        ? (currentPrice - trade.price) * trade.quantity
        : null;
  const pnlPct =
    pnl !== null && trade.price > 0
      ? (pnl / (trade.price * trade.quantity)) * 100
      : null;

  async function saveMemo() {
    setSaving(true);
    try {
      await updateTradeMemo(trade.id, memo);
      onMemoSaved(trade.id, memo);
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {/* 딤 배경 */}
      <div
        onClick={onClose}
        style={{
          position: "fixed", inset: 0, zIndex: 49,
          background: "rgba(0,0,0,0.45)",
          backdropFilter: "blur(4px)",
          WebkitBackdropFilter: "blur(4px)",
        }}
      />

      {/* 모달 */}
      <div style={{
        position: "fixed", zIndex: 50,
        bottom: 0, left: 0, right: 0,
        background: "var(--surface)",
        borderRadius: "20px 20px 0 0",
        padding: "20px 20px 36px",
        boxShadow: "var(--shadow-lg)",
        animation: "slideUp 0.22s ease-out",
        maxWidth: 520, margin: "0 auto",
      }}>
        {/* 헤더 */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 18, fontWeight: 800, letterSpacing: "-0.03em" }}>
              {trade.corp_name}
            </span>
            <span style={{
              fontSize: 11, fontWeight: 700,
              color: label.color, background: label.bg,
              borderRadius: 7, padding: "3px 9px",
            }}>
              {label.text}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 32, height: 32, borderRadius: "50%",
              background: "var(--surface2)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--label2)" strokeWidth="2.2" strokeLinecap="round">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* 거래 정보 */}
        <div style={{
          background: "var(--bg)", borderRadius: 14, padding: "14px 16px",
          marginBottom: 14, display: "flex", flexDirection: "column", gap: 10,
        }}>
          <div style={{ fontSize: 11, color: "var(--label3)", marginBottom: 2 }}>
            {formatDate(trade.created_at)}
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
            <div>
              <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>수량</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{fmt(trade.quantity)}주</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>단가</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{fmt(trade.price)}원</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: "var(--label3)", marginBottom: 3 }}>총액</div>
              <div style={{ fontSize: 15, fontWeight: 700 }}>{fmt(totalAmt)}원</div>
            </div>
          </div>

          {pnl !== null && (
            <div style={{
              borderTop: "0.5px solid var(--sep)", paddingTop: 10,
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <span style={{ fontSize: 11, color: "var(--label3)" }}>
                {trade.trade_type === "sell" ? "실현 손익" : "평가 손익"}
              </span>
              <span style={{
                fontSize: 15, fontWeight: 800,
                color: pnl >= 0 ? "var(--red)" : "var(--primary)",
                letterSpacing: "-0.03em",
              }}>
                {pnl > 0 ? "+" : ""}{fmt(pnl)}원
                {pnlPct !== null && (
                  <span style={{ fontSize: 12, marginLeft: 5 }}>
                    ({pnlPct > 0 ? "+" : ""}{pnlPct.toFixed(1)}%)
                  </span>
                )}
              </span>
            </div>
          )}
        </div>

        {/* 메모 */}
        <div>
          <div style={{ fontSize: 12, fontWeight: 700, color: "var(--label2)", marginBottom: 8 }}>메모</div>
          <textarea
            value={memo}
            onChange={e => setMemo(e.target.value)}
            placeholder="이 거래에 대한 메모를 남겨보세요"
            rows={3}
            style={{
              width: "100%", background: "var(--bg)", borderRadius: 12,
              padding: "10px 14px", fontSize: 14, color: "var(--label)",
              border: "0.5px solid var(--sep)", resize: "none",
              lineHeight: 1.6,
            }}
          />
          <button
            onClick={saveMemo}
            disabled={saving || memo === (trade.memo ?? "")}
            style={{
              marginTop: 8, width: "100%", padding: "11px",
              background: saving || memo === (trade.memo ?? "") ? "var(--surface2)" : "var(--primary)",
              color: saving || memo === (trade.memo ?? "") ? "var(--label3)" : "white",
              borderRadius: 12, fontSize: 14, fontWeight: 700,
              transition: "all 0.18s",
            }}
          >
            {saving ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: TypeScript 검증**

```bash
cd /Users/underove/Desktop/stock-compass/frontend
npx tsc --noEmit 2>&1
```

Expected: 출력 없음

- [ ] **Step 3: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add frontend/components/TradeDetailModal.tsx
git commit -m "feat: add TradeDetailModal component with memo editing"
```

---

## Task 8: TradeJournal 컴포넌트

**Files:**
- Create: `frontend/components/TradeJournal.tsx`

- [ ] **Step 1: TradeJournal.tsx 작성**

```typescript
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  fetchPortfolioSnapshots,
  fetchTradeSummary,
  fetchTrades,
} from "../lib/api";
import type {
  PortfolioSnapshot,
  Trade,
  TradeSummaryItem,
} from "../lib/types";
import { TradeDetailModal } from "./TradeDetailModal";

type ChartMode = "value" | "pnl";
type Period = "1M" | "3M" | "6M" | "1Y";

const PERIOD_DAYS: Record<Period, number> = { "1M": 30, "3M": 90, "6M": 180, "1Y": 365 };

function fmt(n: number) {
  return n.toLocaleString("ko-KR");
}

function fmtShort(n: number) {
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(1)}억`;
  if (abs >= 1e4) return `${Math.round(n / 1e4).toLocaleString()}만`;
  return fmt(n);
}

// ─── SVG 꺾은선 그래프 ────────────────────────────────────────────────────────

function LineChart({
  points,
  isPositive,
  label,
  pctLabel,
}: {
  points: number[];
  isPositive: boolean;
  label: string;
  pctLabel: string;
}) {
  const W = 400;
  const H = 80;
  const PAD = 4;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;

  const coords = points.map((v, i) => {
    const x = PAD + (i / (points.length - 1)) * (W - PAD * 2);
    const y = H - PAD - ((v - min) / range) * (H - PAD * 2);
    return [x, y] as [number, number];
  });

  const polyline = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const lastPt = coords[coords.length - 1];
  const fillPts =
    polyline +
    ` ${lastPt[0].toFixed(1)},${H} ${PAD},${H}`;

  const color = isPositive ? "var(--red)" : "var(--primary)";
  const fillColor = isPositive ? "rgba(255,59,48,0.08)" : "rgba(0,122,255,0.08)";

  return (
    <div style={{ position: "relative" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 6 }}>
        <span style={{ fontSize: 11, color: "var(--label3)", fontWeight: 500 }}>{label}</span>
        <span style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.04em", color }}>
          {pctLabel}
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: "100%", height: 80, display: "block" }}
        preserveAspectRatio="none"
      >
        <polygon points={fillPts} fill={fillColor} />
        <polyline
          points={polyline}
          fill="none"
          stroke={color}
          strokeWidth="1.8"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {/* 마지막 점 강조 */}
        <circle
          cx={lastPt[0]}
          cy={lastPt[1]}
          r="3"
          fill={color}
        />
      </svg>
    </div>
  );
}

// ─── 거래 행 ──────────────────────────────────────────────────────────────────

const TRADE_BADGE: Record<string, { text: string; color: string; bg: string }> = {
  buy:  { text: "매수", color: "var(--primary)", bg: "rgba(0,122,255,0.10)" },
  sell: { text: "매도", color: "var(--red)",     bg: "rgba(255,59,48,0.10)" },
  edit: { text: "수정", color: "var(--label3)",  bg: "var(--surface2)" },
};

function TradeRow({
  trade,
  onClick,
}: {
  trade: Trade;
  onClick: () => void;
}) {
  const badge = TRADE_BADGE[trade.trade_type] ?? TRADE_BADGE.edit;
  const date = trade.created_at.slice(0, 10).replace(/-/g, ".");
  const time = trade.created_at.slice(11, 16);

  return (
    <button
      onClick={onClick}
      style={{
        width: "100%", textAlign: "left",
        padding: "12px 16px",
        display: "flex", alignItems: "center", gap: 12,
        background: "transparent",
        borderRadius: 0,
        transition: "background 0.12s",
      }}
    >
      {/* 타입 뱃지 */}
      <div style={{
        width: 38, height: 38, borderRadius: 11, flexShrink: 0,
        background: badge.bg,
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 11, fontWeight: 700, color: badge.color,
      }}>
        {badge.text}
      </div>

      {/* 종목 + 날짜 */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 700, letterSpacing: "-0.02em", marginBottom: 2 }}>
          {trade.corp_name}
        </div>
        <div style={{ fontSize: 11, color: "var(--label3)" }}>
          {date} {time}
          {trade.memo && (
            <span style={{ marginLeft: 6, color: "var(--label2)" }}>
              · {trade.memo.slice(0, 18)}{trade.memo.length > 18 ? "…" : ""}
            </span>
          )}
        </div>
      </div>

      {/* 수량·단가 */}
      <div style={{ textAlign: "right", flexShrink: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 700, letterSpacing: "-0.02em" }}>
          {fmt(trade.price)}원
        </div>
        <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 1 }}>
          {fmt(trade.quantity)}주
        </div>
      </div>

      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="2" strokeLinecap="round">
        <path d="M9 18l6-6-6-6" />
      </svg>
    </button>
  );
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function TradeJournal() {
  const [chartMode, setChartMode] = useState<ChartMode>("value");
  const [period, setPeriod] = useState<Period>("3M");
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [summary, setSummary] = useState<TradeSummaryItem[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [totalTrades, setTotalTrades] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);

  useEffect(() => {
    setLoading(true);
    Promise.all([
      fetchPortfolioSnapshots(365),
      fetchTradeSummary(),
      fetchTrades({ limit: 100 }),
    ])
      .then(([snapshotRes, summaryRes, tradesRes]) => {
        setSnapshots(snapshotRes.snapshots);
        setSummary(summaryRes.items);
        setTrades(tradesRes.trades);
        setTotalTrades(tradesRes.total);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  // 기간 필터
  const filteredSnapshots = useMemo(() => {
    const days = PERIOD_DAYS[period];
    return snapshots.slice(-days);
  }, [snapshots, period]);

  // 총 평가액 그래프 데이터
  const valuePoints = filteredSnapshots.map(s => s.total_value);
  const valuePct = valuePoints.length >= 2
    ? ((valuePoints[valuePoints.length - 1] - valuePoints[0]) / valuePoints[0]) * 100
    : 0;

  // 실현 손익 누적 그래프 데이터
  const pnlPoints = useMemo(() => {
    let cum = 0;
    return summary.map(s => { cum += s.realized_pnl; return cum; });
  }, [summary]);
  const totalPnl = pnlPoints.length > 0 ? pnlPoints[pnlPoints.length - 1] : 0;

  function handleMemoSaved(id: number, memo: string) {
    setTrades(prev => prev.map(t => t.id === id ? { ...t, memo } : t));
    if (selectedTrade?.id === id) setSelectedTrade(prev => prev ? { ...prev, memo } : null);
  }

  if (loading) {
    return (
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <div style={{ width: 20, height: 20, borderRadius: "50%", border: "2px solid var(--sep)", borderTopColor: "var(--primary)", animation: "spin 0.75s linear infinite" }} />
      </div>
    );
  }

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* ── 그래프 영역 ── */}
      <div style={{ padding: "14px 16px 0", flexShrink: 0 }}>

        {/* 모드 토글 */}
        <div style={{ display: "flex", background: "var(--surface3)", borderRadius: 10, padding: 2, marginBottom: 12 }}>
          {(["value", "pnl"] as ChartMode[]).map(mode => (
            <button
              key={mode}
              onClick={() => setChartMode(mode)}
              style={{
                flex: 1, padding: "6px 8px",
                fontSize: 12, fontWeight: chartMode === mode ? 700 : 500,
                color: chartMode === mode ? "white" : "var(--label2)",
                background: chartMode === mode ? "var(--primary)" : "transparent",
                borderRadius: 8,
                boxShadow: chartMode === mode ? "0 2px 8px rgba(0,122,255,0.28)" : "none",
                transition: "all 0.18s",
              }}
            >
              {mode === "value" ? "총 평가액" : "실현 손익"}
            </button>
          ))}
        </div>

        {/* 그래프 카드 */}
        <div style={{ background: "var(--surface)", borderRadius: 16, padding: "14px 16px 10px", boxShadow: "var(--shadow-sm)", marginBottom: 8 }}>
          {chartMode === "value" ? (
            valuePoints.length >= 2 ? (
              <LineChart
                points={valuePoints}
                isPositive={valuePct >= 0}
                label={`총 평가액 · 최근 ${period}`}
                pctLabel={`${valuePct >= 0 ? "+" : ""}${valuePct.toFixed(1)}%`}
              />
            ) : (
              <div style={{ padding: "20px 0", textAlign: "center" }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--label)", marginBottom: 6 }}>데이터를 모으는 중이에요</div>
                <div style={{ fontSize: 12, color: "var(--label3)" }}>오늘 장 마감 후 첫 기록이 저장됩니다</div>
              </div>
            )
          ) : (
            pnlPoints.length >= 2 ? (
              <LineChart
                points={pnlPoints}
                isPositive={totalPnl >= 0}
                label="실현 손익 누적"
                pctLabel={`${totalPnl >= 0 ? "+" : ""}${fmtShort(totalPnl)}원`}
              />
            ) : (
              <div style={{ padding: "20px 0", textAlign: "center" }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: "var(--label)", marginBottom: 6 }}>아직 실현된 손익이 없어요</div>
                <div style={{ fontSize: 12, color: "var(--label3)" }}>매도 거래가 발생하면 여기에 표시됩니다</div>
              </div>
            )
          )}
        </div>

        {/* 기간 선택 (총 평가액 모드에서만) */}
        {chartMode === "value" && (
          <div style={{ display: "flex", gap: 5, marginBottom: 10 }}>
            {(["1M", "3M", "6M", "1Y"] as Period[]).map(p => (
              <button
                key={p}
                onClick={() => setPeriod(p)}
                style={{
                  padding: "4px 12px",
                  fontSize: 11, fontWeight: 700,
                  color: period === p ? "var(--primary)" : "var(--label3)",
                  background: period === p ? "var(--primary-soft)" : "transparent",
                  borderRadius: 8,
                  transition: "all 0.15s",
                }}
              >
                {p}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ── 거래 이력 리스트 ── */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        <div style={{ padding: "4px 16px 8px", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: "var(--label2)" }}>거래 이력</span>
          <span style={{ fontSize: 11, color: "var(--label3)" }}>총 {totalTrades}건</span>
        </div>

        {trades.length === 0 ? (
          <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", padding: "40px 24px", gap: 12 }}>
            <div style={{ width: 48, height: 48, borderRadius: 15, background: "var(--surface2)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--label3)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
                <line x1="16" y1="13" x2="8" y2="13" />
                <line x1="16" y1="17" x2="8" y2="17" />
              </svg>
            </div>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 14, fontWeight: 700, color: "var(--label)", marginBottom: 5 }}>아직 기록된 거래가 없어요</div>
              <div style={{ fontSize: 12, color: "var(--label3)", lineHeight: 1.7 }}>
                종목을 매수·매도하면<br />자동으로 이곳에 기록됩니다
              </div>
            </div>
          </div>
        ) : (
          <div>
            {trades.map((trade, i) => (
              <div key={trade.id}>
                {i > 0 && <div style={{ height: "0.5px", background: "var(--sep)", marginLeft: 66 }} />}
                <TradeRow trade={trade} onClick={() => setSelectedTrade(trade)} />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 거래 상세 모달 */}
      {selectedTrade && (
        <TradeDetailModal
          trade={selectedTrade}
          onClose={() => setSelectedTrade(null)}
          onMemoSaved={handleMemoSaved}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 검증**

```bash
cd /Users/underove/Desktop/stock-compass/frontend
npx tsc --noEmit 2>&1
```

Expected: 출력 없음

- [ ] **Step 3: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add frontend/components/TradeJournal.tsx
git commit -m "feat: add TradeJournal component with SVG charts and trade history list"
```

---

## Task 9: PortfolioCard — "일지" 탭 추가

**Files:**
- Modify: `frontend/components/PortfolioCard.tsx`

- [ ] **Step 1: Trade Journal import 추가**

파일 상단 imports에 추가:
```typescript
import { TradeJournal } from "./TradeJournal";
```

- [ ] **Step 2: Tab 타입 확장**

기존:
```typescript
type Tab = "stocks" | "watchlist" | "allocation";
```

변경:
```typescript
type Tab = "stocks" | "watchlist" | "allocation" | "journal";
```

- [ ] **Step 3: TabBar 탭 목록에 "일지" 추가**

`TabBar` 컴포넌트 안 `tabs` 배열:
```typescript
const tabs: { key: Tab; label: string }[] = [
  { key: "stocks", label: "내 주식" },
  { key: "watchlist", label: "관심종목" },
  { key: "allocation", label: "배분" },
  { key: "journal", label: "일지" },
];
```

- [ ] **Step 4: 일지 탭 렌더링 블록 추가**

`{/* 배분 탭 */}` 블록 바로 다음에 추가:
```tsx
{/* 일지 탭 */}
{activeTab === "journal" && (
  <TradeJournal />
)}
```

- [ ] **Step 5: TypeScript 검증**

```bash
cd /Users/underove/Desktop/stock-compass/frontend
npx tsc --noEmit 2>&1
```

Expected: 출력 없음

- [ ] **Step 6: 커밋**

```bash
cd /Users/underove/Desktop/stock-compass
git add frontend/components/PortfolioCard.tsx
git commit -m "feat: add 일지 tab to PortfolioCard with TradeJournal"
```

---

## Task 10: 최종 검증 + 배포

**Files:**
- 없음

- [ ] **Step 1: 백엔드 전체 import 검증**

```bash
cd /Users/underove/Desktop/stock-compass/backend
python -c "
from app.db.trade_db import init_db, record_trade, get_trades, update_memo, save_snapshot, get_snapshots, get_realized_summary
from app.api.trades import router
from app.api.portfolio import add_portfolio, remove_portfolio, update_portfolio
from app.scheduler.jobs import job_snapshot_portfolio
print('Backend OK')
"
```

Expected: `Backend OK`

- [ ] **Step 2: 프론트엔드 타입 검증**

```bash
cd /Users/underove/Desktop/stock-compass/frontend
npx tsc --noEmit 2>&1
```

Expected: 출력 없음

- [ ] **Step 3: GitHub push → Railway 자동 배포**

```bash
cd /Users/underove/Desktop/stock-compass
git push origin main
```

- [ ] **Step 4: 동작 확인 체크리스트**

배포 후 다음을 순서대로 확인:

1. PortfolioCard에서 "일지" 탭 클릭 → TradeJournal 렌더링 확인
2. "아직 기록된 거래가 없어요" 빈 상태 표시 확인
3. 종목 추가 → 일지 탭 재진입 → 매수 1건 기록 확인
4. 거래 행 클릭 → TradeDetailModal 열림 확인
5. 메모 입력 후 저장 → 거래 목록에 메모 첫 줄 표시 확인
6. 매도 후 → 실현 손익 탭에 데이터 표시 확인
7. 총 평가액 그래프: 장 마감 후 다음 날 스냅샷 확인 (15:32 KST 이후)
