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

    database_url: str = ""
    supabase_url: str = ""
    supabase_service_key: str = ""

    sentry_dsn: str = ""

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True


settings = Settings()
