# 주식나침반 (Stock Compass)

> AI 기반 주식 정보 팩트체크 웹 서비스 — 받은 리포트·지라시·뉴스를 공식 공시(DART)·뉴스와 교차검증해 신뢰도를 신호등으로 보여줍니다.

투자 정보를 그대로 믿기 전에, 주장의 근거를 공식 출처와 대조해 "믿을 만한지"를 먼저 확인할 수 있도록 만든 서비스입니다.

---

## 주요 기능

| 단계 | 내용 |
|------|------|
| **입력** | PDF 리포트 · 뉴스 URL · 텍스트(지라시)를 그대로 붙여넣기 |
| **교차검증** | RAG로 DART 공시·뉴스에서 근거를 찾아 주장과 대조 |
| **신뢰도 신호등** | 검증 결과를 🟢 신뢰 / 🟡 주의 / 🔴 의심 신호등으로 한눈에 표시 |
| **근거 제시** | 판단의 출처(공시·기사)를 함께 보여 주어 사용자가 직접 확인 가능 |

---

## 기술 스택

- **백엔드**: FastAPI (Python 3.12)
- **프론트**: Next.js + Tailwind + shadcn/ui
- **RAG**: LlamaIndex + Chroma (벡터 DB)
- **LLM**: Gemini Flash (개발) / Claude Sonnet (운영)
- **임베딩**: bge-m3 (로컬) 또는 text-embedding-3-small
- **DB**: PostgreSQL (Supabase) + Redis (Upstash)

---

## 폴더 구조

```
stock-compass/
├── backend/         FastAPI 백엔드
│   ├── app/
│   │   ├── api/          API 엔드포인트
│   │   ├── rag/          RAG 엔진
│   │   ├── parsers/      PDF·URL 파서
│   │   ├── collectors/   외부 데이터 수집기
│   │   ├── db/           DB 클라이언트
│   │   ├── llm/          LLM 래퍼
│   │   └── scheduler/    백그라운드 작업
│   ├── data/             로컬 Chroma 데이터
│   ├── main.py           FastAPI 진입점
│   └── requirements.txt
└── frontend/        Next.js 프론트엔드
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

### 프론트엔드
```bash
cd frontend
npm install
npm run dev
```

브라우저에서 http://localhost:3000 으로 접속합니다.
