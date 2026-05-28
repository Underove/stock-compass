# N.O.V.A iOS 앱 복제 명세 (SwiftUI)

> 목표: **현재 웹 서비스는 그대로 둔 채**, 같은 기능을 SwiftUI 네이티브 앱으로 1:1 복제.
> 앱은 새 프론트일 뿐 **백엔드(`/api/*`)는 지금 것을 그대로 공유**한다.

## 원칙

- 웹 프론트/백엔드 기존 동작은 **건드리지 않음**. 앱을 위한 백엔드 변경은 **순수 추가(additive)**만.
- "복사"는 코드 복붙이 아니라 **화면·기능·정보 구조를 보고 SwiftUI로 동일하게 재현** — 인터랙션은 네이티브 iOS 관용구로.
- API 계약은 백엔드가 자동 노출하는 `/openapi.json`이 단일 소스. 가능하면 **swift-openapi-generator**로 모델·클라이언트 자동 생성.

## 앱 위해 백엔드에 "추가"할 것 (웹 영향 0)

| 추가 | 이유 |
|---|---|
| `POST /api/auth/google-mobile` — Google ID 토큰 검증 → 앱 JWT(`sub`=email, HS256) 발급 | 웹 next-auth는 브라우저 전용. 앱은 못 씀. 기존 `get_current_user`가 받는 JWT를 그대로 발급 |
| `POST /api/auth/apple-mobile` — Apple identity 토큰 검증 → 앱 JWT | **App Store 가이드라인 4.8**: Google 로그인 제공 시 Apple 로그인 필수 |
| `POST /api/devices` — APNs 디바이스 토큰 저장 + 스케줄러 alert→APNs 발송 | 알림이 앱 핵심. 현재 알림 인프라(가격·공시·거래량·기술지표)는 그대로, 발송 채널만 추가 |

> 참고(필수 아님): 지갑 보유종목은 현재 per-user JSON(`portfolio_{user}.json`)으로 저장됨. 앱에서도 같은 백엔드를 쓰므로 동작엔 문제없으나, 신뢰성 위해 DB 테이블로 옮기면 좋음 — 단 이건 웹도 건드리는 일이라 "복제" 범위 밖, 별도 결정.

## 화면 인벤토리 → 사용 API 매핑

### 로그인 (`/login`)
- 웹: next-auth Google
- **앱**: GoogleSignIn + Sign in with Apple → 위 모바일 토큰 엔드포인트 → JWT를 **Keychain** 저장

### 헤더 (전 화면 공통 상단)
- 코스피·코스닥 지수: `GET /api/market/indices` + 실시간 WS `/api/realtime`
- USD/KRW 환율 (외부 frankfurter 또는 market)
- 프로필/로그아웃 → 프로필 화면

### 탭 1 · 지갑 (`PortfolioCard`) — 하위탭: 내주식 / 관심종목 / 배분 / 일지
| 기능 | API |
|---|---|
| 보유 목록 | `GET /api/portfolio` |
| 추가/수정/삭제 | `POST` / `PUT /api/portfolio/{code}` / `DELETE /api/portfolio/{code}` |
| 현재가·차트 | `GET /api/portfolio/price/{code}` · `GET /api/portfolio/chart/{code}` |
| 실시간 시세 | WS `/api/realtime` |
| 알림·인사이트 | `GET /api/portfolio/alerts` · `/api/portfolio/insights` |
| 종목 검색 | `GET /api/portfolio/search` |
| 관심종목 | `GET/POST/DELETE /api/watchlist*` |
| 배분 | 클라이언트 계산 (보유에서) |
| 일지 (`TradeJournal`) | `GET /api/trades` · `/api/trades/summary` · `/api/trades/diagnose` · `/api/portfolio/snapshots` |
| **AI 포트폴리오 분석** | `POST /api/analyze` (구조화 + 출처) · 출처 원본 `GET /api/uploads/{id}/original` |

### 탭 2 · AI 비서 (`ChatCard`) — 하위탭: 브리핑 / 뉴스 / 채팅 / 팩트체크
| 기능 | API |
|---|---|
| AI 브리핑 | `GET /api/portfolio/briefing` |
| 개장 전 뉴스 | `GET/POST` 뉴스 캐시 (notifications) |
| 채팅 | `POST /api/ask/stream` (SSE) — **앱**: `URLSession.bytes`로 SSE, 또는 v1은 비스트리밍 `POST /api/ask` |
| 팩트체크/업로드 (`UploadCard`) | `POST /api/upload` · `GET /api/uploads` · `DELETE /api/uploads/{id}` · `POST /api/factcheck/run` · `GET /api/uploads/{id}/original` |

### 탭 3 · 스크리너 (`ScreenerCard`)
- `POST /api/screener` (조건 필터)

### 종목 상세 모달 (`StockDetailModal`)
- `fetchCommentary` `fetchDisclosures` `fetchFundamental` `fetchTechnical` `fetchTradingFlow` `fetchShortSelling` `fetchStockNews` `getSimilarStocks` `fetchNote/saveNote` `fetchChartData` + 관심종목 추가 / 보유 수정·삭제

### 비교 모달 (`CompareModal`)
- `POST /api/compare` (`fetchCompare`) + `GET /api/portfolio/search`

### 프로필 (`ProfileSettings`)
- `GET /api/profile` · 업데이트

## 웹 패턴 → SwiftUI 매핑 규칙

| 웹 | SwiftUI 네이티브 |
|---|---|
| 하단 3탭 nav | `TabView` (+ `UITabBarAppearance`) |
| 하위탭(세그먼트) | `Picker(.segmented)` 또는 상단 세그먼트 |
| 모달 | `.sheet` / `.fullScreenCover` |
| lightweight-charts | **Swift Charts** |
| 채팅 SSE 스트리밍 | `URLSession.bytes(for:)` async 시퀀스 |
| 실시간 시세 WS | `URLSessionWebSocketTask` |
| Toast/Haptic | 커스텀 overlay / `UIImpactFeedbackGenerator` |
| 숫자 카운트업 | `TimelineView` / `withAnimation` |
| 다크모드 | 자동 (Color assets, `@Environment(\.colorScheme)`) |
| 토큰 보관 | **Keychain** |
| 네트워킹 | `URLSession` actor + `Codable` (또는 swift-openapi-generator) |
| 투자 책임 고지 | 동일 문구 유지 (규제) |

## 권장 빌드 순서

1. **로그인 + 백엔드 모바일 토큰 엔드포인트** (전체 unblocker — 이거 없으면 어떤 API도 못 부름)
2. APIClient(actor) + Keychain + 401 재인증 + (OpenAPI 모델 생성)
3. 헤더(지수·환율) + `TabView` 골격
4. **지갑** (핵심: 보유·시세·실시간·CRUD) → 종목 상세 모달
5. AI 비서 (브리핑 → 채팅 → 팩트체크/업로드)
6. 스크리너
7. 일지 / 비교 / 프로필
8. **푸시(APNs)** + 딥링크
9. App Store 준비: 투자 고지, 개인정보 처리방침, **계정 삭제**, 스크린샷, TestFlight → 심사

## 백엔드 그대로 쓰는 전체 라우터

`auth · analyze · realtime · technical · upload · ask · dart · factcheck · portfolio · market · watchlist · notifications · trades · profile · screener · compare`

— 모두 bearer 토큰 인증 + CORS 허용이라 앱에서 그대로 호출 가능.

---

# 부록: P1 실행 가이드 (백엔드 선작업 — 모두 additive)

## A. 모바일 인증 엔드포인트 (1순위)

기존 `get_current_user`(`app/api/auth.py`)는 HS256 JWT를 `settings.jwt_secret`로 검증하고 `sub`(=email)를 꺼낸다. 모바일 엔드포인트는 **OAuth 제공자 토큰을 검증한 뒤 동일한 모양의 JWT를 발급**하기만 하면 된다 — 나머지 API는 무수정.

### Google (신규 `app/api/auth_mobile.py`)
```python
# 의존성 추가: google-auth
from google.oauth2 import id_token
from google.auth.transport import requests as g_requests
import jwt as pyjwt
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.config import settings

router = APIRouter()
IOS_GOOGLE_CLIENT_ID = "<iOS OAuth 클라이언트 ID>"  # settings로 빼기

class GoogleTokenIn(BaseModel):
    id_token: str

@router.post("/auth/google-mobile")
def google_mobile(body: GoogleTokenIn):
    try:
        info = id_token.verify_oauth2_token(
            body.id_token, g_requests.Request(), IOS_GOOGLE_CLIENT_ID
        )
    except Exception:
        raise HTTPException(401, "유효하지 않은 Google 토큰")
    email = info.get("email")
    if not email:
        raise HTTPException(401, "이메일 없음")
    app_jwt = pyjwt.encode({"sub": email}, settings.jwt_secret, algorithm="HS256")
    return {"access_token": app_jwt, "token_type": "bearer"}
```
- `main.py`에 라우터 등록(additive). 기존 `/api/auth/*`와 충돌 없음.
- **사전 준비**: Google Cloud Console에서 iOS OAuth 클라이언트 생성 → client ID 확보.

### Apple (Sign in with Apple — App Store 필수)
- 앱: `ASAuthorizationAppleIDProvider` → identity token(JWT) 수신.
- 백엔드 `POST /api/auth/apple-mobile`: Apple 공개키(`https://appleid.apple.com/auth/keys`)로 identity token 검증(audience=번들 ID), `email`(또는 `sub`) 추출 → 동일 앱 JWT 발급.
- 주의: Apple은 최초 1회만 email 제공 → 첫 로그인 시 매핑 저장 필요할 수 있음.

## B. 푸시 (APNs)
- 신규 `POST /api/devices` { device_token } → `(username, device_token)` 저장 테이블(additive).
- 스케줄러 alert 잡(가격·공시·거래량·기술지표)이 알림 생성 시 해당 user의 device_token으로 APNs 발송.
- 라이브러리: `aioapns` 또는 `apns2` + APNs **.p8 인증키**(Apple Developer). Firebase 경유도 가능.

## C. Swift 앱 초기 셋업
1. Xcode → iOS App (SwiftUI), iOS 16+.
2. **API 클라이언트**: `swift-openapi-generator` + `swift-openapi-urlsession`
   - 백엔드 `https://<railway>/openapi.json` 저장 → 빌드 플러그인으로 타입·클라이언트 자동 생성.
   - 토큰은 미들웨어로 `Authorization: Bearer` 자동 주입.
3. **Keychain** 토큰 저장 (`KeychainAccess` 등), 401 시 재로그인.
4. **TabView** 3탭(지갑/AI/스크리너) 골격부터.

### APIClient 토큰 주입 스케치 (직접 구현 시)
```swift
actor APIClient {
    static let shared = APIClient()
    private let base = URL(string: "https://<railway>")!
    func get<T: Decodable>(_ path: String) async throws -> T {
        var req = URLRequest(url: base.appending(path: path))
        if let tok = Keychain.token { req.setValue("Bearer \(tok)", forHTTPHeaderField: "Authorization") }
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw APIError.status }
        return try JSONDecoder().decode(T.self, from: data)
    }
}
```

## 사전 준비 체크리스트 (앱 빌드 전)
- [ ] Google Cloud Console iOS OAuth 클라이언트 생성
- [ ] Apple Developer: App ID + Sign in with Apple capability + APNs .p8 키
- [ ] 백엔드 `JWT_SECRET` 32바이트 이상으로 교체 (현재 31바이트)
- [ ] 백엔드에 `/api/auth/google-mobile`(+apple) 추가 후 배포
