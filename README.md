# NOVA — AI 투자 어시스턴트 (구 주식나침반 / Stock Compass)

> 에이전틱 AI가 실시간 시세·공시·기술적 지표·뉴스를 **직접 조회**해 투자 판단을 돕는 웹/모바일 서비스.

LLM이 단순히 답만 하는 게 아니라, function calling으로 필요한 도구를 스스로 호출해 근거 데이터를 모은 뒤 답합니다. 받은 리포트·뉴스의 신뢰도를 공식 공시와 교차검증하는 팩트체크부터, 실시간 차트·스크리너·매매 일지·포트폴리오 분석까지 한 곳에서 다룹니다.

---

## 주요 기능

| 기능 | 내용 |
|------|------|
| **에이전틱 AI 어시스턴트** | LLM이 function calling으로 6개 도구(`get_stock_price`·`get_portfolio`·`search_recent_news`·`get_technical_indicators`·`get_dart_disclosures`·`screen_stocks`)를 직접 호출해 근거 기반 답변 생성 |
| **실시간 시세 & 차트** | 한국투자증권(KIS) REST/WebSocket 기반 실시간 가격·분봉 차트 |
| **AI 포트폴리오 분석** | 보유 종목을 구조화 카드로 분석 + 참고 자료 출처 제시 |
| **투자 정보 팩트체크** | 리포트·뉴스·지라시를 DART 공시·뉴스와 교차검증(pgvector RAG), 신뢰도를 🟢/🟡/🔴 신호등으로 표시 |
| **종목 스크리너** | 조건 기반 종목 필터링 |
| **종목 비교** | 여러 종목을 나란히 비교 |
| **매매 일지** | 거래 기록·실현 손익 관리 |
| **관심종목 AI 신호** | 관심종목에 대한 AI 한 줄 신호 |
| **투자 프로필** | 목표·경험 기반 개인화 |
| **알림 & 푸시** | iOS APNs 푸시 알림 |
| **iOS 앱** | SwiftUI 네이티브 앱으로 마이그레이션 진행 — 웹과 동일 백엔드 공유, 모바일 소셜 로그인 지원 |

> ⚠️ 본 서비스는 투자 참고용 정보를 제공하며, 투자 판단과 책임은 이용자 본인에게 있습니다.

---

## 기술 스택

- **백엔드**: FastAPI (Python 3.12)
- **프론트**: Next.js + Tailwind + shadcn/ui
- **인증**: NextAuth (웹) + 소셜 로그인 (모바일)
- **LLM**: OpenAI gpt-5.x (reasoning) + Google Gemini — function calling(tool use) 기반
- **RAG**: pgvector (PostgreSQL) + Gemini 임베딩
- **데이터 소스**: 한국투자증권(KIS) REST·WebSocket, KRX, DART 공시, 네이버(외인·기관 순매수), 웹 검색
- **DB**: PostgreSQL (Supabase)
- **푸시**: APNs (HTTP/2)
- **모니터링**: Sentry
- **iOS**: SwiftUI

---

## 폴더 구조

```
stock-compass/
├── backend/                 FastAPI 백엔드
│   └── app/
│       ├── api/             엔드포인트 (analyze·ask·factcheck·realtime·screener·trades·portfolio·compare 등 18개)
│       ├── collectors/      데이터 수집기 (kis_rest·kis_ws·krx·dart·web_search·ta_engine)
│       ├── rag/             팩트체크 / QA RAG (factcheck.py·qa.py)
│       ├── llm/             LLM 래퍼 (openai_llm·gemini)
│       ├── tools.py         function calling 도구 정의·실행
│       ├── push/            APNs 푸시
│       ├── scheduler/       백그라운드 작업
│       ├── parsers/         PDF·URL 파서
│       ├── db/              DB 클라이언트
│       └── config.py
├── frontend/                Next.js (App Router)
│   └── app/
│       ├── api/auth/        NextAuth
│       ├── login/
│       └── ...
└── docs/                    iOS 마이그레이션 명세 + 기능별 spec/plan
```

---

## 셋업 & 실행

### 백엔드
```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

환경 변수(`.env`)에 KIS·OpenAI·Gemini·DART API 키, PostgreSQL 접속 정보, (선택) Sentry DSN·APNs 키가 필요합니다.

### 프론트엔드
```bash
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:3000 으로 접속합니다.
