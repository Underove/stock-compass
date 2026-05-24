from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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

    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True


settings = Settings()
