# Sub-project D: 알림 고도화 (Alert Enhancement) — Design Spec

> **For agentic workers:** Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this spec.

**Goal:** 기존 목표가/손절가 알림에 공시·거래량·기술지표 알림을 추가하고, SQLite 기반 유저별 알림으로 전환한다.

**Architecture:** 기존 `alerts_log.json` 파일 방식을 `compass.db` SQLite로 마이그레이션. 스케줄러 job 3개 추가, API 인증 추가, AlertDropdown에 모니터링 종목 관리 UI 추가.

**Tech Stack:** FastAPI, SQLite (aiosqlite 없이 동기), APScheduler(CronTrigger KST), Next.js, React

---

## 1. DB 스키마

`compass.db`에 테이블 2개 추가 (기존 try/except ALTER 패턴 대신 CREATE IF NOT EXISTS 사용):

```sql
CREATE TABLE IF NOT EXISTS alerts (
  id          TEXT PRIMARY KEY,
  user_email  TEXT NOT NULL,
  type        TEXT NOT NULL,
  stock_code  TEXT NOT NULL,
  corp_name   TEXT NOT NULL,
  message     TEXT NOT NULL,
  meta        TEXT,
  created_at  TEXT NOT NULL,
  read        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alert_watch (
  user_email  TEXT NOT NULL,
  stock_code  TEXT NOT NULL,
  corp_name   TEXT NOT NULL,
  PRIMARY KEY (user_email, stock_code)
);
```

**`alerts.type` 값:**
- `target` — 목표가 도달 (기존)
- `stop_loss` — 손절가 도달 (기존)
- `dart` — 신규 공시
- `volume_spike` — 거래량 급등 (전일比 2배↑)
- `rsi_overbought` — RSI ≥ 70
- `rsi_oversold` — RSI ≤ 30
- `golden_cross` — 5MA가 20MA 상향 돌파
- `dead_cross` — 5MA가 20MA 하향 돌파

**`alert_id` 중복 방지 패턴:**
- `{stock_code}_target_{YYYY-MM-DD}`
- `{stock_code}_stop_loss_{YYYY-MM-DD}`
- `{stock_code}_dart_{rcept_no}`
- `{stock_code}_volume_{YYYY-MM-DD}`
- `{stock_code}_rsi_overbought_{YYYY-MM-DD}`
- `{stock_code}_rsi_oversold_{YYYY-MM-DD}`
- `{stock_code}_golden_cross_{YYYY-MM-DD}`
- `{stock_code}_dead_cross_{YYYY-MM-DD}`

---

## 2. 모니터링 대상 종목 결정 로직

각 스케줄러 job에서 유저별로:

```python
def _get_monitored_stocks(user_email: str) -> list[dict]:
    """포트폴리오 + 관심종목 + alert_watch 합집합 (중복 제거)."""
    seen = set()
    result = []
    for item in get_portfolio_items(user_email):       # 기존 함수
        if item["stock_code"] not in seen:
            seen.add(item["stock_code"])
            result.append({"stock_code": item["stock_code"], "corp_name": item["corp_name"]})
    for item in get_watchlist_items(user_email):        # 기존 함수
        if item["stock_code"] not in seen:
            seen.add(item["stock_code"])
            result.append({"stock_code": item["stock_code"], "corp_name": item["corp_name"]})
    for item in get_alert_watch(user_email):            # 신규
        if item["stock_code"] not in seen:
            seen.add(item["stock_code"])
            result.append({"stock_code": item["stock_code"], "corp_name": item["corp_name"]})
    return result
```

---

## 3. 스케줄러 Jobs

### 기존 `job_check_price_alerts()` 수정
- 포트폴리오를 `portfolio_*.json` glob → DB `get_portfolio_items(user_email)` 조회로 변경
- 알림을 `alerts_log.json` → `alerts` DB 테이블로 저장
- 모든 등록 유저를 순회하며 체크

### 신규 `job_check_dart_alerts()` — 16:40 KST
```
- 모든 유저의 모니터링 종목 수집
- 종목별 DART fetch_recent_disclosures() 호출 (오늘 날짜 필터)
- rcept_no 기반 중복 체크 후 신규 공시만 alert 저장
- meta: {"rcept_no": "...", "report_nm": "...", "rcept_dt": "..."}
```

### 신규 `job_check_volume_alerts()` — 16:45 KST
```
- screener_snapshot에서 volume_ratio 조회
- 없으면 ta_engine.analyze()로 직접 계산 (폴백)
- volume_ratio >= 2.0 인 종목 중 모니터링 대상만 필터
- meta: {"volume_ratio": 2.3}
```

### 신규 `job_check_technical_alerts()` — 16:50 KST
```
- screener_snapshot에서 rsi, cross_5_20 조회
- 없으면 ta_engine.analyze()로 직접 계산 (폴백)
- 조건 체크:
    rsi >= 70  → rsi_overbought, meta: {"rsi": 73.2}
    rsi <= 30  → rsi_oversold,   meta: {"rsi": 28.1}
    cross_5_20 == "golden" → golden_cross
    cross_5_20 == "dead"   → dead_cross
- 각 조건 하루 1회 중복 방지
```

---

## 4. API 엔드포인트

### 수정: `notifications.py`

```python
# 기존 엔드포인트 — 인증 추가
GET  /api/notifications/alerts          # Depends(get_current_user), user_email 기준 조회
POST /api/notifications/alerts/read     # Depends(get_current_user), user_email 기준 처리

# 신규 엔드포인트
GET    /api/notifications/watch          # 수동 추가 종목 목록 반환
POST   /api/notifications/watch          # { stock_code, corp_name } 추가
DELETE /api/notifications/watch/{code}   # 종목 제거
```

### `trade_db.py` 신규 함수

```python
def init_alert_tables()              # CREATE TABLE IF NOT EXISTS 2개
def insert_alert(alert: dict)        # id 중복 시 무시 (INSERT OR IGNORE)
def get_unread_alerts(user_email)    # read=0 조회, 최신순
def mark_alerts_read(user_email, ids: list[str])
def get_alert_watch(user_email)      # alert_watch 조회
def add_alert_watch(user_email, stock_code, corp_name)
def remove_alert_watch(user_email, stock_code)
def get_all_user_emails()            # 스케줄러에서 전체 유저 순회용
```

---

## 5. 프론트엔드

### `lib/types.ts` 수정
```typescript
export type AlertType =
  | "target" | "stop_loss"
  | "dart" | "volume_spike"
  | "rsi_overbought" | "rsi_oversold"
  | "golden_cross" | "dead_cross";

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

### `lib/api.ts` 수정
```typescript
// PriceAlert → Alert 타입으로 교체
fetchAlerts(): Promise<Alert[]>
markAlertsRead(ids: string[]): Promise<void>
fetchAlertWatch(): Promise<WatchStock[]>
addAlertWatch(stock_code: string, corp_name: string): Promise<void>
removeAlertWatch(stock_code: string): Promise<void>
```

### `app/page.tsx` — AlertDropdown 개편

드롭다운 레이아웃:
```
┌────────────────────────────────┐
│ 알림              [모두 읽음]   │
├────────────────────────────────┤
│ 모니터링 종목                   │
│ [삼성전자 ×][카카오 ×][+ 추가]  │
├────────────────────────────────┤
│ 🔵 공시   삼성전자 분기보고서   │
│ 🟠 거래량  카카오 2.3배 급등    │
│ 🟣 기술   SK하이닉스 골든크로스 │
│ 🔴 손절   LG화학 손절가 도달   │
└────────────────────────────────┘
```

알림 타입별 색상 (CSS 변수 활용):
- `dart`: `var(--primary)` (파랑)
- `volume_spike`: `var(--orange)` (주황)
- `rsi_overbought`, `rsi_oversold`, `golden_cross`, `dead_cross`: `#BF5AF2` (보라)
- `target`: `var(--green)` (초록)
- `stop_loss`: `var(--red)` (빨강)

모니터링 종목 칩: `alert_watch` 수동 추가 종목만 표시 (포트폴리오/관심종목은 자동 포함이라 별도 표시 불필요). 검색 → 추가 → X 삭제.

---

## 6. 에러 처리

- 각 스케줄러 job은 try/except로 종목 단위 실패 격리 (한 종목 실패가 전체 job을 중단하지 않음)
- DART API 실패 시 해당 종목 스킵, 로그 warning
- screener_snapshot 미존재 시 ta_engine 폴백, ta_engine도 실패 시 스킵
- API 인증 실패 시 401 반환

---

## 7. 파일 변경 목록

| 파일 | 변경 |
|------|------|
| `backend/app/db/trade_db.py` | alert 테이블 생성 + CRUD 함수 8개 추가 |
| `backend/app/scheduler/jobs.py` | 기존 job 수정 + 신규 job 3개 추가 |
| `backend/main.py` | 신규 job 3개 스케줄러 등록 |
| `backend/app/api/notifications.py` | 인증 추가 + watch API 3개 추가 |
| `frontend/lib/types.ts` | Alert 타입 교체, WatchStock 추가 |
| `frontend/lib/api.ts` | PriceAlert → Alert, watch API 함수 추가 |
| `frontend/app/page.tsx` | AlertDropdown 개편, 모니터링 종목 관리 UI |
