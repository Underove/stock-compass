# Sub-project C: 종목 스크리너 + 유사종목 추천

**날짜:** 2026-05-26  
**상태:** 설계 확정

---

## 개요

사용자가 섹터·기본적 지표·기술적 지표 조건으로 한국 주식을 필터링하고, 결과 종목 또는 유사종목을 탭해 차트·공시까지 이어지는 종목 발굴 플로우를 제공한다. 채팅에서도 자연어로 동일한 스크리너 엔진을 호출할 수 있다.

---

## 아키텍처 전체 흐름

```
[스케줄러 평일 16:10]
  └→ pykrx 배치: 전 종목 PER·PBR·시가총액·섹터·모멘텀 → screener_snapshot 테이블

[스케줄러 평일 16:20]
  └→ 시총 상위 300개에만 ta_engine.analyze() → rsi·ma_status 업데이트

[사용자 필터 요청]
  └→ POST /api/screener
        ① screener_snapshot에서 조건 매칭 (has_ta=true 우선) → 최대 50개
        ② 결과 반환 (TA 미포함 종목은 rsi/ma_status null)

[유사종목 요청]
  └→ GET /api/screener/similar/{stock_code}
        ① 타겟 종목 프로파일 조회
        ② 섹터 일치 → PER·시가총액·모멘텀 유사도 계산 → 상위 5개 반환

[채팅 Function Calling]
  └→ screen_stocks 도구 → 자연어 파싱 → 같은 screener_snapshot 엔진 호출
```

---

## 데이터 레이어

### screener_snapshot 테이블 (trade_db.py에 추가)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| stock_code | TEXT PK | KRX 종목코드 6자리 |
| corp_name | TEXT | 종목명 |
| sector | TEXT | 섹터 (KRX 업종 분류) |
| market_cap | INTEGER | 시가총액 (억 원) |
| per | REAL | PER (음수·null 허용) |
| pbr | REAL | PBR |
| momentum_20d | REAL | 20일 수익률 (%) |
| rsi | REAL | RSI(14), 시총 300위 이하면 NULL |
| ma_status | TEXT | golden/dead/above/below/none, 300위 이하면 NULL |
| has_ta | INTEGER | 1=TA 완료, 0=미완료 |
| updated_at | TEXT | 마지막 갱신 일자 (YYYY-MM-DD) |

CRUD: `get_screener_snapshot()`, `upsert_screener_snapshot()`, `query_screener()`

---

## 백엔드

### 신규 파일: backend/app/api/screener.py

```
POST /api/screener
  인증: 필요 (Depends get_current_user)
  body:
    sector: str | None
    market_cap_min: int | None  (억 원)
    market_cap_max: int | None
    per_max: float | None
    pbr_max: float | None
    rsi_min: float | None
    rsi_max: float | None
    ma_status: "golden" | "dead" | "above" | "below" | None
  응답: list[ScreenerItem] (최대 50개, has_ta=true 우선 정렬)

GET /api/screener/similar/{stock_code}
  인증: 필요
  응답: list[SimilarItem] (5개)
    유사도 계산: 섹터 일치 필터 → PER·시총·모멘텀 정규화 후 유클리드 거리
```

### 신규 파일: backend/app/collectors/screener_collector.py

- `fetch_all_fundamentals()`: pykrx `get_market_fundamental_by_ticker()` 배치 호출
- `fetch_sector_map()`: pykrx `get_market_sector_ticker_list()`로 섹터별 종목코드 역매핑
- `compute_momentum(stock_code)`: 최근 20거래일 수익률 계산

### 스케줄러 추가 (jobs.py)

```python
# 평일 16:10 KST — 전 종목 기본적 지표 스냅샷
scheduler.add_job(refresh_screener_fundamentals, "cron",
                  day_of_week="mon-fri", hour=7, minute=10, timezone="UTC")

# 평일 16:20 KST — 시총 상위 300개 TA 계산
scheduler.add_job(refresh_screener_ta, "cron",
                  day_of_week="mon-fri", hour=7, minute=20, timezone="UTC")
```

### Function Calling 도구 추가 (tools.py)

```python
FunctionDeclaration(
    name="screen_stocks",
    description="섹터·RSI·MA·PER 조건으로 종목을 스크리닝한다. "
                "'반도체 RSI 과매도', '저PER 황금십자' 같은 요청 시 호출.",
    parameters={
        "type": "object",
        "properties": {
            "sector": {"type": "string"},
            "rsi_max": {"type": "number"},
            "rsi_min": {"type": "number"},
            "ma_status": {"type": "string", "enum": ["golden", "dead", "above", "below"]},
            "per_max": {"type": "number"},
            "market_cap_min": {"type": "number"},
        },
    },
)
```

---

## 프론트엔드

### 신규 파일: frontend/components/ScreenerCard.tsx

**구조:**
```
ScreenerCard
  ├── 섹터 칩 (ProfileSettings 섹터 칩 패턴 재사용, 단일 선택)
  ├── 조건 행: PER 최대 입력 / RSI 범위 (min~max) / MA 상태 드롭다운
  ├── "스크리닝" 버튼
  ├── 결과 리스트
  │     └── ScreenerRow: 종목명·현재가·등락률·RSI·PER
  │           └── 탭 → StockDetailModal 열림
  │                 └── "유사종목" 섹션 (하단 추가)
  │                       └── 유사종목 5개 칩
  │                             └── 탭 → StockDetailModal 열림
  └── 빈 상태: "조건을 설정하고 스크리닝해보세요"
```

**API 연동:** `lib/api.ts`에 `screenStocks()`, `getSimilarStocks()` 추가

### 수정: frontend/components/StockDetailModal.tsx

- 하단에 "유사종목" 섹션 추가
- `GET /api/screener/similar/{stock_code}` 호출
- 유사종목 5개 칩 → 탭 시 동일 모달 재열림 (stock_code 교체)

### 수정: frontend/app/page.tsx

- `<ScreenerCard />` 메인 페이지 하단 추가

### 수정: frontend/lib/api.ts

```typescript
screenStocks(params: ScreenerParams): Promise<ScreenerItem[]>
getSimilarStocks(stockCode: string): Promise<SimilarItem[]>
```

### 수정: frontend/lib/types.ts

```typescript
type ScreenerItem = {
  stock_code: string; corp_name: string; sector: string;
  market_cap: number; per: number | null; pbr: number | null;
  momentum_20d: number; rsi: number | null; ma_status: string | null;
}
type SimilarItem = {
  stock_code: string; corp_name: string; sector: string;
  per: number | null; market_cap: number; similarity_score: number;
}
```

---

## 에러 처리

- 스냅샷 미갱신 (장 없는 날 등): `updated_at` 기준 3일 이상 오래되면 응답에 `stale: true` 플래그
- pykrx 조회 실패: 해당 종목 스킵, 로그만 기록
- TA 계산 실패: `has_ta=0` 유지, 필터에서 제외하지 않고 rsi/ma_status null로 반환
- 유사종목 없음 (섹터 데이터 부족): 빈 배열 반환

---

## 범위 외 (이번 구현에서 제외)

- 실시간 필터 (입력할 때마다 자동 갱신) — 버튼 클릭 방식으로 충분
- 필터 조건 저장/즐겨찾기
- 시총 300위 이하 종목 TA 온디맨드 계산
- 스크리너 결과 CSV 내보내기 (Sub-project H에서)
