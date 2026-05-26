# Sub-project F: 종목 비교 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 두 종목을 모달에서 나란히 비교하는 기능 구현 — 수익률 차트(기간 선택) + 지표 테이블(PER/PBR/RSI 등) + 3곳 진입점(스크리너/상세모달/포트폴리오).

**Architecture:** FastAPI `GET /api/compare` 엔드포인트 1개(pykrx 가격 이력 + SQLite screener_snapshot 지표), 신규 `CompareModal.tsx` 컴포넌트(lightweight-charts LineSeries 2개 + 지표 테이블), 기존 컴포넌트 3곳에 "비교" 버튼 진입점 추가.

**Tech Stack:** FastAPI, pykrx, SQLite, Next.js 16, React, lightweight-charts (already installed at `frontend/node_modules/lightweight-charts`)

---

## 파일 변경 목록

| 파일 | 변경 |
|------|------|
| `backend/app/api/compare.py` | 신규 — GET /api/compare 엔드포인트 |
| `backend/main.py` | compare router import + include_router 등록 |
| `backend/tests/test_compare_api.py` | 신규 — 엔드포인트 테스트 |
| `frontend/lib/types.ts` | CompareStock, CompareResponse 타입 추가 |
| `frontend/lib/api.ts` | fetchCompare 함수 + 타입 re-export 추가 |
| `frontend/components/CompareModal.tsx` | 신규 — 비교 모달 전체 구현 |
| `frontend/components/ScreenerCard.tsx` | "비교" 버튼 + CompareModal 연결 |
| `frontend/components/StockDetailModal.tsx` | "비교" 버튼 + CompareModal 연결 |
| `frontend/components/PortfolioCard.tsx` | "비교" 버튼 + CompareModal 연결 |

---

## Task 1: 백엔드 GET /api/compare 엔드포인트

**Files:**
- Create: `backend/app/api/compare.py`
- Modify: `backend/main.py`
- Create: `backend/tests/test_compare_api.py`

**Context:** 기존 API 파일(`backend/app/api/notifications.py`) 패턴을 따른다. DB 연결은 `trade_db._conn()` 재사용. pykrx 호출은 `_get_price_series()`로 격리하여 테스트에서 monkeypatch 가능하게 구성.

- [ ] **Step 1: 테스트 파일 작성 (실패 확인용)**

`backend/tests/test_compare_api.py` 생성:

```python
"""GET /api/compare 엔드포인트 테스트."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.db.trade_db as trade_db
    trade_db._DB_PATH = tmp_path / "test.db"
    trade_db.init_db()

    trade_db.upsert_screener_snapshot([
        {
            "stock_code": "005930", "corp_name": "삼성전자", "sector": "전기·전자",
            "market_cap": 2980000, "per": 19.2, "pbr": 1.3,
            "momentum_20d": -2.1, "rsi": 48.3, "ma_status": "below", "has_ta": 1,
            "volume_ratio": 0.9, "foreign_net_buy": -124000000000, "disclosure_30d": 0,
        },
        {
            "stock_code": "000660", "corp_name": "SK하이닉스", "sector": "전기·전자",
            "market_cap": 1120000, "per": 12.4, "pbr": 1.8,
            "momentum_20d": 8.4, "rsi": 62.1, "ma_status": "golden", "has_ta": 1,
            "volume_ratio": 2.3, "foreign_net_buy": 382000000000, "disclosure_30d": 0,
        },
    ])

    # pykrx 네트워크 호출 차단 — _get_price_series 직접 대체
    import app.api.compare as compare_mod
    monkeypatch.setattr(
        compare_mod, "_get_price_series",
        lambda code, start, end: [
            {"date": "2026-03-01", "close": 58400, "return_pct": 0.0},
            {"date": "2026-03-04", "close": 57900, "return_pct": -0.86},
        ],
    )

    from main import app
    return TestClient(app)


def test_compare_basic(client):
    r = client.get("/api/compare?codes=005930,000660&period=3m")
    assert r.status_code == 200
    body = r.json()
    assert body["period"] == "3m"
    assert len(body["stocks"]) == 2
    codes = {s["stock_code"] for s in body["stocks"]}
    assert codes == {"005930", "000660"}


def test_compare_metrics(client):
    r = client.get("/api/compare?codes=005930,000660")
    body = r.json()
    samsung = next(s for s in body["stocks"] if s["stock_code"] == "005930")
    assert samsung["corp_name"] == "삼성전자"
    assert samsung["metrics"]["per"] == pytest.approx(19.2)
    assert samsung["metrics"]["volume_ratio"] == pytest.approx(0.9)
    assert samsung["price_series"][0]["return_pct"] == pytest.approx(0.0)


def test_compare_requires_two_codes(client):
    assert client.get("/api/compare?codes=005930").status_code == 400
    assert client.get("/api/compare?codes=005930,000660,207940").status_code == 400


def test_compare_missing_stock_returns_null_metrics(client):
    """screener_snapshot에 없는 종목은 corp_name·metrics 모두 null."""
    r = client.get("/api/compare?codes=005930,999999")
    assert r.status_code == 200
    body = r.json()
    unknown = next(s for s in body["stocks"] if s["stock_code"] == "999999")
    assert unknown["corp_name"] is None
    assert unknown["metrics"]["per"] is None
    assert unknown["metrics"]["market_cap"] is None
```

- [ ] **Step 2: 테스트 실패 확인**

```bash
cd backend && python -m pytest tests/test_compare_api.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'app.api.compare'` 또는 404 에러

- [ ] **Step 3: compare.py 구현**

`backend/app/api/compare.py` 생성:

```python
"""종목 비교 API."""
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.collectors.krx import krx_stock
from app.db.trade_db import _conn

router = APIRouter()
_KST = timezone(timedelta(hours=9))
_METRIC_KEYS = (
    "market_cap", "per", "pbr", "rsi",
    "momentum_20d", "volume_ratio", "foreign_net_buy",
)


@router.get("/compare")
def compare_stocks(codes: str, period: str = "3m"):
    code_list = [c.strip() for c in codes.split(",")]
    if len(code_list) != 2:
        raise HTTPException(400, "codes는 정확히 2개여야 합니다")

    period_days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}.get(period, 90)
    end = datetime.now(_KST).date()
    start = end - timedelta(days=period_days)

    result = []
    for code in code_list:
        info = _get_metrics(code)
        corp_name = info.pop("corp_name", None)
        sector = info.pop("sector", None)
        price_series = _get_price_series(code, start, end)
        result.append({
            "stock_code": code,
            "corp_name": corp_name,
            "sector": sector,
            "metrics": info,
            "price_series": price_series,
        })

    return {"stocks": result, "period": period}


def _get_metrics(stock_code: str) -> dict:
    with _conn() as con:
        row = con.execute(
            """SELECT corp_name, sector, market_cap, per, pbr, rsi,
                      momentum_20d, volume_ratio, foreign_net_buy
               FROM screener_snapshot WHERE stock_code=?""",
            (stock_code,),
        ).fetchone()
    if not row:
        return {"corp_name": None, "sector": None, **{k: None for k in _METRIC_KEYS}}
    return {k: row[k] for k in row.keys()}


def _get_price_series(stock_code: str, start: date, end: date) -> list[dict]:
    try:
        df = krx_stock.get_market_ohlcv_by_date(
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), stock_code
        )
        if df.empty:
            return []
        base = int(df.iloc[0]["종가"])
        series = []
        for dt, row in df.iterrows():
            close = int(row["종가"])
            series.append({
                "date": dt.strftime("%Y-%m-%d"),
                "close": close,
                "return_pct": round((close - base) / base * 100, 2) if base else 0.0,
            })
        return series
    except Exception:
        return []
```

- [ ] **Step 4: main.py에 router 등록**

`backend/main.py`를 열어 두 곳을 수정:

**import 추가** (기존 `from app.api import screener as screener_api` 바로 뒤에):
```python
from app.api import compare as compare_api  # noqa: E402
```

**include_router 추가** (기존 `app.include_router(screener_api.router, ...)` 바로 뒤에):
```python
app.include_router(compare_api.router, prefix="/api", tags=["compare"])
```

- [ ] **Step 5: import 검증**

```bash
cd backend && python -c "from app.api.compare import router; print('compare OK')"
```

Expected: `compare OK`

- [ ] **Step 6: 테스트 통과 확인**

```bash
cd backend && python -m pytest tests/test_compare_api.py -v
```

Expected: 4 tests PASS

- [ ] **Step 7: 커밋**

```bash
git add backend/app/api/compare.py backend/main.py backend/tests/test_compare_api.py
git commit -m "feat: GET /api/compare 엔드포인트 추가 (Sub-project F)"
```

---

## Task 2: 프론트엔드 타입 + API 함수

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`

**Context:** `types.ts`에 타입을 단독 정의하고 `api.ts`에서 import + re-export한다. 기존 타입들은 파일 말미에 추가한다. `api.ts`의 import 블록(파일 상단 1~35줄 범위)에 새 타입을 추가하고, 기존 `export type { Alert as PriceAlert }` 줄 바로 뒤에 새 re-export를 넣는다.

- [ ] **Step 1: types.ts에 타입 추가**

`frontend/lib/types.ts` 말미에 추가:

```typescript
export type CompareStock = {
  stock_code: string;
  corp_name: string | null;
  sector: string | null;
  metrics: {
    market_cap: number | null;
    per: number | null;
    pbr: number | null;
    rsi: number | null;
    momentum_20d: number | null;
    volume_ratio: number | null;
    foreign_net_buy: number | null;
  };
  price_series: { date: string; close: number; return_pct: number }[];
};

export type CompareResponse = {
  stocks: [CompareStock, CompareStock];
  period: string;
};
```

- [ ] **Step 2: api.ts import 블록에 타입 추가**

`frontend/lib/api.ts` 파일 상단 `import type { ... } from "./types"` 블록 안에 `CompareStock,` 과 `CompareResponse,` 를 추가한다. 기존 `WatchStock,` 줄 바로 뒤에 삽입:

```typescript
  WatchStock,
  CompareStock,
  CompareResponse,
```

- [ ] **Step 3: api.ts에 re-export + fetchCompare 추가**

`frontend/lib/api.ts`에서 `export type { Alert as PriceAlert } from "./types";` 줄 바로 뒤에 추가:

```typescript
export type { CompareStock, CompareResponse };
```

그리고 파일 말미(마지막 export 함수 뒤)에 추가:

```typescript
export async function fetchCompare(
  codeA: string,
  codeB: string,
  period: string,
): Promise<CompareResponse> {
  return getJSON(`/api/compare?codes=${codeA},${codeB}&period=${period}`);
}
```

- [ ] **Step 4: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i error | head -10
```

Expected: 에러 0개

- [ ] **Step 5: 커밋**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat: CompareStock/CompareResponse 타입 + fetchCompare API 함수 추가"
```

---

## Task 3: CompareModal.tsx 전체 구현

**Files:**
- Create: `frontend/components/CompareModal.tsx`

**Context:**
- 모달 스타일: `position: fixed, inset: 0` 바텀 시트 (승인된 layout-v3.html 디자인)
- 차트: `StockChart.tsx`(line 37-38)와 동일한 dynamic import 패턴 사용 (`await import("lightweight-charts")`)
- 종목 검색: `searchStock()` 재사용 (`GET /api/portfolio/search?q=...`), `SearchResult = { corp_code, corp_name, stock_code }`
- 색상: 종목 A `#007AFF`, 종목 B `#FF9500`, 더 좋은 값 `#30D158`

- [ ] **Step 1: CompareModal.tsx 생성**

`frontend/components/CompareModal.tsx` 생성 (전체 파일):

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

import { fetchCompare, searchStock } from "../lib/api";
import type { CompareResponse, CompareStock, SearchResult } from "../lib/types";

type Props = {
  initialCode?: string;
  initialName?: string;
  onClose: () => void;
};

type Slot = { code: string; name: string };
type MetricKey = keyof CompareStock["metrics"];

// ─── 포맷 헬퍼 ────────────────────────────────────────────────────────────────

function fmtNum(v: number | null): string {
  return v === null ? "–" : v.toFixed(1);
}
function fmtPct(v: number | null): string {
  if (v === null) return "–";
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}
function fmtMarketCap(v: number | null): string {
  if (v === null) return "–";
  // market_cap 단위: 억원. 10000억 = 1조
  if (v >= 10000) return `${(v / 10000).toFixed(0)}조`;
  return `${Math.round(v).toLocaleString("ko-KR")}억`;
}
function fmtForeignNet(v: number | null): string {
  if (v === null) return "–";
  // foreign_net_buy 단위: 원. 1억원 = 1e8
  const billions = Math.round(Math.abs(v) / 1e8);
  return `${v >= 0 ? "+" : "–"}${billions.toLocaleString("ko-KR")}억`;
}
function fmtRatio(v: number | null): string {
  return v === null ? "–" : `${v.toFixed(1)}x`;
}

// ─── 더 좋은 값 판단 ──────────────────────────────────────────────────────────

function better(key: MetricKey, a: number | null, b: number | null): "A" | "B" | null {
  if (a === null || b === null) return null;
  const lowerBetter = key === "per" || key === "pbr";
  if (lowerBetter) return a < b ? "A" : b < a ? "B" : null;
  return a > b ? "A" : b > a ? "B" : null;
}

// ─── 지표 행 설정 ─────────────────────────────────────────────────────────────

const ROWS: { label: string; key: MetricKey; fmt: (v: number | null) => string }[] = [
  { label: "시가총액",      key: "market_cap",     fmt: fmtMarketCap  },
  { label: "PER",          key: "per",            fmt: fmtNum        },
  { label: "PBR",          key: "pbr",            fmt: fmtNum        },
  { label: "RSI",          key: "rsi",            fmt: fmtNum        },
  { label: "20일 모멘텀",   key: "momentum_20d",   fmt: fmtPct        },
  { label: "거래량 비율",   key: "volume_ratio",   fmt: fmtRatio      },
  { label: "외국인 순매수", key: "foreign_net_buy", fmt: fmtForeignNet },
];

// ─── 기간 선택 옵션 ───────────────────────────────────────────────────────────

const PERIODS: { key: "1m" | "3m" | "6m" | "1y"; label: string }[] = [
  { key: "1m", label: "1M" },
  { key: "3m", label: "3M" },
  { key: "6m", label: "6M" },
  { key: "1y", label: "1Y" },
];

// ─── 수익률 차트 ──────────────────────────────────────────────────────────────

function ReturnChart({ data }: { data: CompareResponse }) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const chartRef = useRef<any>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const s0 = data.stocks[0].price_series;
    const s1 = data.stocks[1].price_series;
    if (s0.length === 0 && s1.length === 0) return;

    let mounted = true;

    async function init() {
      const { createChart, LineSeries } = await import("lightweight-charts");
      if (!mounted || !containerRef.current) return;
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }

      const chart = createChart(containerRef.current, {
        width: containerRef.current.clientWidth,
        height: 140,
        layout: {
          background: { color: "transparent" },
          textColor: "#8E8E93",
          fontSize: 10,
          fontFamily: "-apple-system, BlinkMacSystemFont, 'Pretendard Variable', sans-serif",
        },
        grid: {
          vertLines: { color: "rgba(60,60,67,0.06)" },
          horzLines: { color: "rgba(60,60,67,0.06)" },
        },
        rightPriceScale: {
          borderVisible: false,
          textColor: "#AEAEB2",
          scaleMargins: { top: 0.1, bottom: 0.1 },
        },
        timeScale: {
          borderVisible: false,
          tickMarkFormatter: (t: unknown) => {
            if (typeof t === "string") {
              const p = (t as string).split("-");
              return `${parseInt(p[1])}/${parseInt(p[2])}`;
            }
            return String(t);
          },
        },
        handleScroll: false,
        handleScale: false,
      });
      chartRef.current = chart;

      if (s0.length > 0) {
        const seriesA = chart.addSeries(LineSeries, {
          color: "#007AFF",
          lineWidth: 2 as const,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesA.setData(s0.map(p => ({ time: p.date, value: p.return_pct })));
      }
      if (s1.length > 0) {
        const seriesB = chart.addSeries(LineSeries, {
          color: "#FF9500",
          lineWidth: 2 as const,
          priceLineVisible: false,
          lastValueVisible: true,
        });
        seriesB.setData(s1.map(p => ({ time: p.date, value: p.return_pct })));
      }
      chart.timeScale().fitContent();
    }

    init();
    return () => {
      mounted = false;
      if (chartRef.current) { chartRef.current.remove(); chartRef.current = null; }
    };
  }, [data]);

  return <div ref={containerRef} style={{ width: "100%" }} />;
}

// ─── 종목 슬롯 카드 ───────────────────────────────────────────────────────────

function StockSlot({
  slot, color, label, isSearching, onOpen, onClose: onSlotClose,
  query, onQueryChange, results, searching, onSelect,
}: {
  slot: Slot | null;
  color: string;
  label: string;
  isSearching: boolean;
  onOpen: () => void;
  onClose: () => void;
  query: string;
  onQueryChange: (q: string) => void;
  results: SearchResult[];
  searching: boolean;
  onSelect: (r: SearchResult) => void;
}) {
  return (
    <div style={{ position: "relative" }}>
      <div
        onClick={isSearching ? undefined : onOpen}
        style={{
          border: `1.5px solid ${color}`,
          borderRadius: 12,
          padding: "10px 14px",
          cursor: isSearching ? "default" : "pointer",
          minHeight: 62,
        }}
      >
        <div style={{ fontSize: 10, fontWeight: 600, color, letterSpacing: "0.3px", marginBottom: 3 }}>
          {label}
        </div>
        {isSearching ? (
          <input
            autoFocus
            value={query}
            onChange={e => onQueryChange(e.target.value)}
            placeholder="종목명 검색..."
            style={{
              width: "100%",
              border: "none",
              outline: "none",
              fontSize: 13,
              fontWeight: 700,
              background: "transparent",
              color: "var(--label)",
              letterSpacing: "-0.3px",
            }}
          />
        ) : (
          <>
            <div style={{
              fontWeight: 700,
              fontSize: 14,
              letterSpacing: "-0.3px",
              color: slot ? "var(--label)" : "var(--label3)",
            }}>
              {slot ? slot.name : "종목 선택"}
            </div>
            {slot && (
              <div style={{ fontSize: 11, color: "var(--label3)", marginTop: 1, fontFamily: "monospace" }}>
                {slot.code}
              </div>
            )}
          </>
        )}
      </div>

      {/* 검색 드롭다운 */}
      {isSearching && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 4px)",
          left: 0,
          right: 0,
          background: "var(--surface)",
          borderRadius: 12,
          boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
          zIndex: 10,
          maxHeight: 200,
          overflowY: "auto",
        }}>
          {searching && (
            <div style={{ padding: "10px 14px", fontSize: 12, color: "var(--label3)" }}>검색 중...</div>
          )}
          {!searching && results.length === 0 && query.trim() && (
            <div style={{ padding: "10px 14px", fontSize: 12, color: "var(--label3)" }}>결과 없음</div>
          )}
          {results.map(r => (
            <div
              key={r.stock_code}
              onClick={() => onSelect(r)}
              style={{
                padding: "9px 14px",
                cursor: "pointer",
                borderTop: "0.5px solid var(--sep)",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--label)" }}>{r.corp_name}</div>
                <div style={{ fontSize: 11, color: "var(--label3)", fontFamily: "monospace" }}>{r.stock_code}</div>
              </div>
            </div>
          ))}
          <div
            onClick={onSlotClose}
            style={{
              padding: "9px 14px",
              cursor: "pointer",
              borderTop: "0.5px solid var(--sep)",
              fontSize: 12,
              color: "var(--label3)",
              textAlign: "center",
            }}
          >
            닫기
          </div>
        </div>
      )}
    </div>
  );
}

// ─── 메인 컴포넌트 ────────────────────────────────────────────────────────────

export function CompareModal({ initialCode, initialName, onClose }: Props) {
  const [stockA, setStockA] = useState<Slot | null>(
    initialCode ? { code: initialCode, name: initialName ?? "" } : null,
  );
  const [stockB, setStockB] = useState<Slot | null>(null);
  const [period, setPeriod] = useState<"1m" | "3m" | "6m" | "1y">("3m");
  const [data, setData] = useState<CompareResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [searchSlot, setSearchSlot] = useState<"A" | "B" | null>(null);
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // 두 종목 모두 선택되면 자동 조회
  useEffect(() => {
    if (!stockA || !stockB) return;
    setLoading(true);
    fetchCompare(stockA.code, stockB.code, period)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [stockA, stockB, period]);

  // 검색어 300ms 디바운스
  useEffect(() => {
    if (!query.trim()) { setSearchResults([]); return; }
    const timer = setTimeout(async () => {
      setSearching(true);
      try {
        const results = await searchStock(query);
        setSearchResults(results);
      } finally {
        setSearching(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [query]);

  function selectStock(r: SearchResult) {
    const slot: Slot = { code: r.stock_code, name: r.corp_name };
    if (searchSlot === "A") setStockA(slot);
    else setStockB(slot);
    setSearchSlot(null);
    setQuery("");
    setSearchResults([]);
  }

  return (
    <>
      {/* 백드롭 */}
      <div
        onClick={onClose}
        style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)", zIndex: 199 }}
      />

      {/* 바텀 시트 패널 */}
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 200,
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            width: "100%",
            maxWidth: 480,
            maxHeight: "92vh",
            background: "var(--bg)",
            borderRadius: "20px 20px 0 0",
            overflowY: "auto",
            pointerEvents: "auto",
          }}
        >
          {/* 헤더 */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "16px 20px 0" }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: "var(--label)" }}>종목 비교</span>
            <button
              onClick={onClose}
              style={{
                background: "none", border: "none", cursor: "pointer",
                fontSize: 16, color: "var(--label2)", padding: "4px 6px",
              }}
            >
              ✕
            </button>
          </div>

          {/* 종목 슬롯 */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 32px 1fr", alignItems: "flex-start", gap: 8, padding: "16px 20px 0" }}>
            <StockSlot
              slot={stockA} color="#007AFF" label="종목 A"
              isSearching={searchSlot === "A"}
              onOpen={() => { setSearchSlot("A"); setQuery(""); setSearchResults([]); }}
              onClose={() => setSearchSlot(null)}
              query={query} onQueryChange={setQuery}
              results={searchResults} searching={searching}
              onSelect={selectStock}
            />
            <div style={{ textAlign: "center", fontSize: 11, fontWeight: 700, color: "var(--label3)", paddingTop: 22 }}>
              VS
            </div>
            <StockSlot
              slot={stockB} color="#FF9500" label="종목 B"
              isSearching={searchSlot === "B"}
              onOpen={() => { setSearchSlot("B"); setQuery(""); setSearchResults([]); }}
              onClose={() => setSearchSlot(null)}
              query={query} onQueryChange={setQuery}
              results={searchResults} searching={searching}
              onSelect={selectStock}
            />
          </div>

          {/* 기간 선택 */}
          <div style={{ display: "flex", gap: 6, padding: "16px 20px" }}>
            {PERIODS.map(p => (
              <button
                key={p.key}
                onClick={() => setPeriod(p.key)}
                style={{
                  fontSize: 12, padding: "5px 12px", borderRadius: 7,
                  border: "none", cursor: "pointer",
                  background: period === p.key ? "#007AFF" : "rgba(118,118,128,0.12)",
                  color: period === p.key ? "#fff" : "var(--label2)",
                  fontWeight: period === p.key ? 700 : 500,
                }}
              >
                {p.label}
              </button>
            ))}
          </div>

          {/* 로딩 상태 */}
          {loading && (
            <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--label3)" }}>
              불러오는 중...
            </div>
          )}

          {/* 데이터 영역 */}
          {!loading && data && (
            <>
              {/* 레전드 */}
              <div style={{ display: "flex", gap: 20, padding: "0 20px 10px" }}>
                {([0, 1] as const).map(i => {
                  const s = data.stocks[i];
                  const ret = s.price_series.at(-1)?.return_pct ?? null;
                  const color = i === 0 ? "#007AFF" : "#FF9500";
                  const retColor = ret === null ? "var(--label2)" : ret >= 0 ? "var(--red)" : "var(--primary)";
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <div style={{ width: 24, height: 2.5, background: color, borderRadius: 2, flexShrink: 0 }} />
                      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--label)" }}>
                        {s.corp_name ?? s.stock_code}
                      </span>
                      {ret !== null && (
                        <span style={{ fontSize: 12, fontWeight: 700, color: retColor }}>
                          {ret >= 0 ? "+" : ""}{ret.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>

              {/* 차트 */}
              <div style={{ padding: "0 20px 16px" }}>
                {data.stocks[0].price_series.length === 0 && data.stocks[1].price_series.length === 0 ? (
                  <div style={{
                    height: 140,
                    display: "flex", alignItems: "center", justifyContent: "center",
                    fontSize: 12, color: "var(--label3)",
                  }}>
                    가격 데이터 없음
                  </div>
                ) : (
                  <ReturnChart data={data} />
                )}
              </div>

              {/* 구분선 */}
              <div style={{ height: "0.5px", background: "var(--sep)" }} />

              {/* 지표 테이블 */}
              <div style={{ padding: "4px 0 8px" }}>
                {/* 헤더 행 */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 80px 80px", padding: "6px 20px", marginBottom: 2 }}>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "var(--label3)", letterSpacing: "0.3px" }}>지표</span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "#007AFF", textAlign: "right" }}>
                    {data.stocks[0].corp_name ?? data.stocks[0].stock_code}
                  </span>
                  <span style={{ fontSize: 10, fontWeight: 600, color: "#FF9500", textAlign: "right" }}>
                    {data.stocks[1].corp_name ?? data.stocks[1].stock_code}
                  </span>
                </div>

                {/* 지표 행 */}
                {ROWS.map(row => {
                  const vA = data.stocks[0].metrics[row.key];
                  const vB = data.stocks[1].metrics[row.key];
                  const win = better(row.key, vA, vB);
                  return (
                    <div
                      key={row.key}
                      style={{
                        display: "grid",
                        gridTemplateColumns: "1fr 80px 80px",
                        padding: "9px 20px",
                        borderTop: "0.5px solid rgba(118,118,128,0.12)",
                      }}
                    >
                      <span style={{ fontSize: 13, color: "var(--label2)" }}>{row.label}</span>
                      <span style={{
                        fontSize: 13, textAlign: "right",
                        fontWeight: win === "A" ? 700 : 500,
                        color: win === "A" ? "#30D158" : "var(--label)",
                      }}>
                        {row.fmt(vA)}
                      </span>
                      <span style={{
                        fontSize: 13, textAlign: "right",
                        fontWeight: win === "B" ? 700 : 500,
                        color: win === "B" ? "#30D158" : "var(--label)",
                      }}>
                        {row.fmt(vB)}
                      </span>
                    </div>
                  );
                })}
              </div>

              {/* 하단 safe area */}
              <div style={{ height: 24 }} />
            </>
          )}

          {/* 에러 상태 */}
          {!loading && !data && stockA && stockB && (
            <div style={{ padding: "24px 20px", textAlign: "center", fontSize: 13, color: "var(--label3)" }}>
              데이터를 불러오지 못했습니다
            </div>
          )}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 2: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

Expected: 에러 0개

- [ ] **Step 3: 커밋**

```bash
git add frontend/components/CompareModal.tsx
git commit -m "feat: CompareModal 컴포넌트 구현 (차트 + 지표 테이블)"
```

---

## Task 4: 진입점 3곳 연결

**Files:**
- Modify: `frontend/components/ScreenerCard.tsx`
- Modify: `frontend/components/StockDetailModal.tsx`
- Modify: `frontend/components/PortfolioCard.tsx`

**Context:**
- 각 파일에 `compareOpen`, `compareCode`, `compareName` 상태 3개 추가
- "비교" 버튼은 `e.stopPropagation()` 포함
- CompareModal zIndex(200)가 StockDetailModal zIndex(100)보다 높아 내부 렌더링도 정상 표시됨

### 4-1. ScreenerCard.tsx

`ScreenerCard` 함수(line 69)의 상태 선언부(`const [selectedItem, ...` 바로 뒤)에 추가:

```tsx
const [compareOpen, setCompareOpen] = useState(false);
const [compareCode, setCompareCode] = useState("");
const [compareName, setCompareName] = useState("");

function openCompare(code: string, name: string) {
  setCompareCode(code);
  setCompareName(name);
  setCompareOpen(true);
}
```

파일 상단 import에 추가:

```tsx
import { CompareModal } from "./CompareModal";
```

스크리너 결과 각 행(line ~297, `<div key={item.stock_code} onClick={...}>` 안)에서 신호 배지 `<div>` 안(`{item.per != null && ...}` 바로 뒤)에 "비교" 버튼 추가:

```tsx
{/* 비교 버튼 */}
<button
  onClick={e => { e.stopPropagation(); openCompare(item.stock_code, item.corp_name); }}
  style={{
    padding: "3px 8px",
    borderRadius: 6,
    background: "rgba(0,122,255,0.08)",
    color: "var(--primary)",
    fontSize: 11, fontWeight: 700,
    border: "none", cursor: "pointer",
  }}
>
  비교
</button>
```

`{selectedItem && <StockDetailModal ... />}` 바로 뒤에 CompareModal 렌더링 추가:

```tsx
{compareOpen && (
  <CompareModal
    initialCode={compareCode}
    initialName={compareName}
    onClose={() => setCompareOpen(false)}
  />
)}
```

### 4-2. StockDetailModal.tsx

파일 상단 import에 추가:

```tsx
import { CompareModal } from "./CompareModal";
```

컴포넌트 상단 상태 선언부(line ~42, `const [currentItem, ...` 바로 뒤)에 추가:

```tsx
const [compareOpen, setCompareOpen] = useState(false);
```

헤더 버튼 그룹(line ~279-314, 관심종목 버튼과 닫기 버튼 사이)에 "비교" 버튼 추가:

```tsx
<button
  onClick={() => setCompareOpen(true)}
  style={{
    height: 32, borderRadius: 16, padding: "0 12px",
    background: "var(--surface2)",
    fontSize: 12, fontWeight: 700,
    color: "var(--label2)", flexShrink: 0,
    border: "none", cursor: "pointer",
  }}
>
  비교
</button>
```

컴포넌트 return JSX 말미(닫는 `</div>` 바로 앞)에 추가:

```tsx
{compareOpen && (
  <CompareModal
    initialCode={currentItem.stock_code}
    initialName={currentItem.corp_name}
    onClose={() => setCompareOpen(false)}
  />
)}
```

### 4-3. PortfolioCard.tsx

`StockRow` 함수 props 타입(line 509-513)에 `onCompare` 추가:

```tsx
function StockRow({ item, onClick, onEdit, onPriceLoaded, alertCount, realtimePrice, isEditing, sparkPoints, onCompare }: {
  item: PortfolioItem; onClick: () => void; onEdit: () => void;
  onPriceLoaded: (code: string, price: StockPrice) => void;
  alertCount: number; realtimePrice?: RealtimePrice; isEditing: boolean;
  sparkPoints?: number[];
  onCompare?: () => void;
})
```

`StockRow` 내 "거래" 버튼 div(line ~616) 바로 뒤에 "비교" 버튼 추가:

```tsx
{onCompare && (
  <div style={{ flexShrink: 0 }} onClick={e => e.stopPropagation()}>
    <button
      onClick={onCompare}
      style={{
        padding: "6px 11px", borderRadius: 9,
        background: "var(--surface2)",
        color: "var(--label2)",
        fontSize: 12, fontWeight: 700,
        minWidth: 44, minHeight: 32,
        border: "none", cursor: "pointer",
      }}
    >
      비교
    </button>
  </div>
)}
```

`PortfolioCard` 함수(line 1007)의 상태 선언부에 추가:

```tsx
const [compareOpen, setCompareOpen] = useState(false);
const [compareCode, setCompareCode] = useState("");
const [compareName, setCompareName] = useState("");
```

파일 상단 import에 추가:

```tsx
import { CompareModal } from "./CompareModal";
```

`StockRow` 렌더링(line ~1153)에 `onCompare` prop 추가:

```tsx
<StockRow
  item={item}
  onClick={() => { setEditingCode(null); setSelected(item); }}
  onEdit={() => setEditingCode(editingCode === item.stock_code ? null : item.stock_code)}
  onPriceLoaded={handlePriceLoaded}
  alertCount={alerts[item.stock_code] ?? 0}
  realtimePrice={realtimePrices[item.stock_code]}
  isEditing={editingCode === item.stock_code}
  sparkPoints={sparklines[item.stock_code]}
  onCompare={() => { setCompareCode(item.stock_code); setCompareName(item.corp_name); setCompareOpen(true); }}
/>
```

`{selected && <StockDetailModal ... />}` 바로 뒤에 CompareModal 렌더링 추가:

```tsx
{compareOpen && (
  <CompareModal
    initialCode={compareCode}
    initialName={compareName}
    onClose={() => setCompareOpen(false)}
  />
)}
```

- [ ] **Step 1: ScreenerCard.tsx 수정** (위의 4-1 변경 적용)

- [ ] **Step 2: StockDetailModal.tsx 수정** (위의 4-2 변경 적용)

- [ ] **Step 3: PortfolioCard.tsx 수정** (위의 4-3 변경 적용)

- [ ] **Step 4: TypeScript 검증**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep -i error | head -20
```

Expected: 에러 0개

- [ ] **Step 5: 커밋**

```bash
git add frontend/components/ScreenerCard.tsx frontend/components/StockDetailModal.tsx frontend/components/PortfolioCard.tsx
git commit -m "feat: 스크리너/상세모달/포트폴리오에 비교 버튼 진입점 추가"
```
