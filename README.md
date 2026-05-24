# 주식나침반 (Stock Compass)

AI 기반 주식 정보 팩트체크 웹 서비스. 사용자가 받은 리포트·지라시·뉴스를 공식 공시(DART)·뉴스와 교차검증하여 신뢰도를 신호등으로 표시한다.

## 기술 스택

- **백엔드**: FastAPI (Python 3.12)
- **프론트**: Next.js + Tailwind + shadcn/ui
- **RAG**: LlamaIndex + Chroma (벡터 DB)
- **LLM**: Gemini Flash (개발) / Claude Sonnet (운영)
- **임베딩**: bge-m3 (로컬) 또는 text-embedding-3-small
- **DB**: PostgreSQL (Supabase) + Redis (Upstash)

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

## 개발 실행

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

브라우저: http://localhost:3000
