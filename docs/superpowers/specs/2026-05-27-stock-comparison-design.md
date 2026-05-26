# Sub-project F: 종목 비교 (Stock Comparison) — Design Spec

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this spec.

**Goal:** 두 종목을 모달에서 나란히 비교 — 수익률 차트(기간 선택) + 지표 테이블(PER/PBR/RSI 등)

**Architecture:** 신규 API 엔드포인트 1개, 신규 프론트엔드 컴포넌트 1개, 기존 3곳에 진입점 추가.

**Tech Stack:** FastAPI, pykrx(가격 이력), SQLite screener_snapshot(지표), Next.js 16, React, lightweight-charts

---

## 1. 백엔드 — `GET /api/compare`

### 엔드포인트

```
GET /api/compare?codes=005930,000660&period=3m
```

- `codes`: 콤마 구분 종목코드 2개. 2개 초과 시 400 반환.
- `period`: `1m` | `3m` | `6m` | `1y` (기본값 `3m`)
- 인증: 불필요 (공개 데이터)

### 응답 형식

```json
{
  "stocks": [
    {
      "stock_code": "005930",
      "corp_name": "삼성전자",
      "sector": "전기·전자",
      "metrics": {
        "market_cap": 2980000,
        "per": 19.2,
        "pbr": 1.3,
        "rsi": 48.3,
        "momentum_20d": -2.1,
        "volume_ratio": 0.9,
        "foreign_net_buy": -124000000000
      },
      "price_series": [
        {"date": "2026-03-01", "close": 58400, "return_pct": 0.0},
        {"date": "2026-03-04", "close": 57900, "return_pct": -0.86},
        ...
      ]
    },
    {
      "stock_code": "000660",
      ...
    }
  ],
  "period": "3m"
}
```

- `return_pct`: 첫 거래일 종가 기준 수익률 (%), 100 기준 정규화 대신 % 방식 사용
- `metrics`의 None 필드는 `null`로 반환

### 구현 로직

```python
# backend/app/api/compare.py

@router.get("/compare")
def compare_stocks(codes: str, period: str = "3m"):
    code_list = [c.strip() for c in codes.split(",")]
    if len(code_list) != 2:
        raise HTTPException(400, "codes는 정확히 2개여야 합니다")

    period_days = {"1m": 30, "3m": 90, "6m": 180, "1y": 365}.get(period, 90)
    end = datetime.now(KST).date()
    start = end - timedelta(days=period_days)

    result = []
    for code in code_list:
        # 지표: screener_snapshot에서 조회 (corp_name, sector 포함)
        info = _get_metrics(code)
        corp_name = info.pop("corp_name", None)
        sector = info.pop("sector", None)
        # 가격 이력: pykrx get_market_ohlcv_by_date
        price_series = _get_price_series(code, start, end)
        result.append({
            "stock_code": code,
            "corp_name": corp_name,
            "sector": sector,
            "metrics": info,
            "price_series": price_series,
        })

    return {"stocks": result, "period": period}
```

### `_get_price_series()` 구현

```python
from app.collectors.krx import krx_stock  # pykrx stock module

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

### `_get_metrics()` 구현

```python
def _get_metrics(stock_code: str) -> dict:
    with _conn() as con:
        row = con.execute(
            """SELECT corp_name, sector, market_cap, per, pbr, rsi,
                      momentum_20d, volume_ratio, foreign_net_buy
               FROM screener_snapshot WHERE stock_code=?""",
            (stock_code,),
        ).fetchone()
    if not row:
        return {}
    return {k: row[k] for k in row.keys()}
```

---

## 2. 프론트엔드 — `CompareModal.tsx`

### 파일 위치
`frontend/components/CompareModal.tsx`

### Props

```typescript
type CompareModalProps = {
  initialCode?: string;   // 진입 종목 코드 (슬롯 A에 미리 채워짐)
  initialName?: string;   // 진입 종목명
  onClose: () => void;
};
```

### 상태

```typescript
const [stockA, setStockA] = useState<{code:string; name:string} | null>(initialCode ? {code: initialCode, name: initialName??''} : null);
const [stockB, setStockB] = useState<{code:string; name:string} | null>(null);
const [period, setPeriod] = useState<"1m"|"3m"|"6m"|"1y">("3m");
const [data, setData] = useState<CompareResponse | null>(null);
const [loading, setLoading] = useState(false);
const [searchSlot, setSearchSlot] = useState<"A"|"B"|null>(null);
const [query, setQuery] = useState("");
const [searchResults, setSearchResults] = useState<{stock_code:string; corp_name:string}[]>([]);
```

### 레이아웃 (승인된 디자인 기반)

```
┌─────────────────────────────────────┐
│  [종목 A 카드 (파랑)]  VS  [종목 B 카드 (주황)] │
│  [1M] [3M★] [6M] [1Y]              │
│  ─ 삼성전자 -2.1%  ─ SK하이닉스 +8.4% │
│  [수익률 비교 차트 lightweight-charts] │
│  ─────────────────────────────────  │
│  지표    삼성전자   SK하이닉스        │
│  시가총액  298조     112조           │
│  PER     19.2      12.4 ★          │
│  PBR     1.3       1.8             │
│  RSI     48.3      62.1 ★          │
│  모멘텀   -2.1%     +8.4% ★        │
│  거래량   0.9x      2.3x ★         │
│  외국인   -1,240억  +3,820억 ★      │
└─────────────────────────────────────┘
```

- ★ = 더 좋은 값 bold + 색상 강조
- 지표 "더 좋은 값" 기준:
  - PER, PBR → 낮을수록 유리 (단, null 제외)
  - RSI, 모멘텀, 거래량비율, 외국인순매수, 시가총액 → 높을수록 유리

### 종목 선택 UX

- 카드 클릭 → 인라인 검색창 오픈 (`searchSlot = "A"` 또는 `"B"`)
- 검색어 입력 → 300ms 디바운스 → `GET /api/search?q=...` 호출
- 결과 목록에서 선택 → 해당 슬롯에 set, 검색창 닫기
- 두 종목 모두 채워지면 자동으로 `fetchCompare()` 호출

### 차트

- `lightweight-charts` `LineChart` 또는 두 `LineSeries` 겹치기
- x축: 날짜, y축: 수익률 (%)
- 종목 A: `#007AFF`, 종목 B: `#FF9500`
- 기간 버튼 클릭 → `period` 변경 → `fetchCompare()` 재호출

### API 함수 (`lib/api.ts` 추가)

```typescript
export type CompareStock = {
  stock_code: string;
  corp_name: string;
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

export async function fetchCompare(
  codeA: string,
  codeB: string,
  period: string
): Promise<CompareResponse> {
  return getJSON(`/api/compare?codes=${codeA},${codeB}&period=${period}`);
}
```

---

## 3. 진입점 3곳

### 3-1. 스크리너 카드 (`ScreenerCard.tsx`)

종목 행 오른쪽에 "비교" 버튼 추가:
```tsx
<button onClick={() => openCompare(stock.stock_code, stock.corp_name)}>
  비교
</button>
```

### 3-2. 종목 상세 모달 (`StockDetailModal.tsx`)

모달 헤더 영역에 "비교" 버튼 추가.

### 3-3. 포트폴리오 카드 (`PortfolioCard.tsx`)

포트폴리오 종목 행에 "비교" 버튼 추가.

### 공통 패턴

각 진입점에서:
```tsx
const [compareOpen, setCompareOpen] = useState(false);
const [compareCode, setCompareCode] = useState("");
const [compareName, setCompareName] = useState("");

function openCompare(code: string, name: string) {
  setCompareCode(code);
  setCompareName(name);
  setCompareOpen(true);
}

// JSX
{compareOpen && (
  <CompareModal
    initialCode={compareCode}
    initialName={compareName}
    onClose={() => setCompareOpen(false)}
  />
)}
```

---

## 4. 에러 처리

- pykrx 조회 실패 시 `price_series: []` 반환, 차트 영역에 "가격 데이터 없음" 표시
- screener_snapshot에 종목 없으면 metrics 전부 `null`, 테이블에 "-" 표시
- 두 종목 모두 선택되지 않은 상태에서는 차트/테이블 미렌더링

---

## 5. 파일 변경 목록

| 파일 | 변경 |
|------|------|
| `backend/app/api/compare.py` | 신규 — GET /api/compare |
| `backend/main.py` | compare router 등록 |
| `frontend/components/CompareModal.tsx` | 신규 |
| `frontend/lib/api.ts` | fetchCompare, CompareStock, CompareResponse 추가 |
| `frontend/lib/types.ts` | CompareStock, CompareResponse 타입 추가 |
| `frontend/components/ScreenerCard.tsx` | "비교" 버튼 + CompareModal 연결 |
| `frontend/components/StockDetailModal.tsx` | "비교" 버튼 + CompareModal 연결 |
| `frontend/components/PortfolioCard.tsx` | "비교" 버튼 + CompareModal 연결 |
