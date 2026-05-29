from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"
    gemini_embedding_model: str = "text-embedding-004"

    dart_api_key: str = ""
    naver_client_id: str = ""
    naver_client_secret: str = ""

    kis_app_key: str = ""
    kis_app_secret: str = ""
    kis_is_mock: bool = True

    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_model_pro: str = "gpt-5.4"

    jwt_secret: str = "change-me-in-production"

    # 모바일(iOS) 소셜 로그인 — 미설정 시 모바일 인증 엔드포인트 비활성(503)
    google_ios_client_id: str = ""
    apple_bundle_id: str = ""

    # APNs 푸시 — 미설정(키 비어있음) 시 푸시 발송은 조용히 skip (알림 저장은 정상)
    apns_key_p8: str = ""          # .p8 키 내용 (PEM). 줄바꿈은 실제 개행 또는 "\n" 모두 허용
    apns_key_id: str = ""          # 키 ID (10자)
    apns_team_id: str = ""         # Apple Developer Team ID (10자)
    apns_bundle_id: str = "com.underove.NOVA"
    apns_use_sandbox: bool = True  # 개발 빌드=sandbox, TestFlight/App Store=프로덕션(False)

    database_url: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    sentry_dsn: str = ""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True


settings = Settings()
