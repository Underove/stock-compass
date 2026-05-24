import json
import logging
import re
import time
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY가 .env에 설정되지 않았습니다")
    return genai.Client(api_key=settings.gemini_api_key)


EMBEDDING_BATCH_SIZE = 25  # Gemini가 큰 배치를 거부하면 SDK 에러 메시지가 망가짐


def embed_texts(
    texts: list[str],
    task_type: str = "RETRIEVAL_DOCUMENT",
) -> list[list[float]]:
    """텍스트 리스트를 Gemini 임베딩 벡터로 변환. 큰 배치는 자동 분할."""
    if not texts:
        return []
    client = get_client()
    config = types.EmbedContentConfig(task_type=task_type)
    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + EMBEDDING_BATCH_SIZE]
        result = client.models.embed_content(
            model=settings.gemini_embedding_model,
            contents=batch,
            config=config,
        )
        all_vectors.extend(e.values for e in result.embeddings)
    return all_vectors


def embed_query(query: str) -> list[float]:
    """검색 질의용 임베딩."""
    return embed_texts([query], task_type="RETRIEVAL_QUERY")[0]


def generate_answer(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.3,
    _retries: int = 2,
) -> str:
    """프롬프트를 Gemini에 보내고 자연어 답변을 받음. 503 과부하 시 재시도."""
    client = get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        temperature=temperature,
    )
    last_exc: Exception | None = None
    for attempt in range(_retries + 1):
        try:
            result = client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=config,
            )
            return (result.text or "").strip()
        except Exception as e:
            last_exc = e
            msg = str(e)
            is_transient = "503" in msg or "UNAVAILABLE" in msg or "429" in msg or "RESOURCE_EXHAUSTED" in msg
            if is_transient and attempt < _retries:
                wait = 2 ** attempt  # 1s, 2s
                logger.warning("Gemini 일시 오류 (재시도 %d/%d): %s", attempt + 1, _retries, msg[:120])
                time.sleep(wait)
                continue
            break
    raise RuntimeError("AI 서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.") from last_exc


def parse_json_response(response: str, default: dict) -> dict:
    """LLM 응답에서 JSON 객체 추출. 마크다운 코드블록 안에 있어도 처리."""
    cleaned = response.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{[\s\S]*\}", response)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return default
