import json
import logging
import re
import time
from functools import lru_cache

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

# Placeholder so tests can patch app.llm.gemini.execute_tool before generate_with_tools is called.
# The real binding is set lazily on first call to generate_with_tools() to avoid circular imports.
execute_tool = None  # type: ignore[assignment]


@lru_cache(maxsize=1)
def get_client() -> genai.Client:
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY가 .env에 설정되지 않았습니다")
    return genai.Client(api_key=settings.gemini_api_key, http_options={"timeout": 90})


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
    """프롬프트를 LLM에 보내고 자연어 답변을 받음. openai_api_key 설정 시 OpenAI 사용."""
    if settings.openai_api_key:
        from app.llm.openai_llm import generate_answer as _openai_generate
        return _openai_generate(prompt, system_instruction=system_instruction, temperature=temperature, _retries=_retries)

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
                wait = 2 ** attempt
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


def _safe_text(result) -> str:
    """result.text를 안전하게 추출. function_call 파트가 섞여 있어도 처리."""
    try:
        return (result.text or "").strip()
    except (ValueError, AttributeError):
        parts = result.candidates[0].content.parts if result and result.candidates else []
        return " ".join(p.text for p in parts if getattr(p, "text", None)).strip()


def _has_function_call(part) -> bool:
    """파트에 실제 function_call이 있는지 안전하게 확인."""
    fc = getattr(part, "function_call", None)
    return fc is not None and bool(getattr(fc, "name", None))


def generate_with_tools(
    prompt: str,
    system_instruction: str | None = None,
    username: str | None = None,
    temperature: float = 0.3,
    max_tool_calls: int = 3,
) -> str:
    """RAG 프롬프트를 LLM에 보내고 Function Calling 루프 후 최종 텍스트 반환. openai_api_key 설정 시 OpenAI 사용.

    도구 호출이 있으면 execute_tool()로 실행 → 결과를 컨텍스트에 추가 → 재호출.
    최대 max_tool_calls회까지만 반복. 503/429 에러는 generate_answer()와 동일하게 재시도.
    """
    if settings.openai_api_key:
        from app.llm.openai_llm import generate_with_tools as _openai_generate_with_tools
        return _openai_generate_with_tools(prompt, system_instruction=system_instruction, username=username, temperature=temperature, max_tool_calls=max_tool_calls)

    import sys
    from app.tools import GEMINI_TOOLS, execute_tool as _execute_tool  # noqa: PLC0415

    # Expose execute_tool at module level so tests can patch app.llm.gemini.execute_tool
    _mod = sys.modules[__name__]
    if getattr(_mod, "execute_tool", None) is None:
        _mod.execute_tool = _execute_tool  # type: ignore[attr-defined]

    client = get_client()
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=GEMINI_TOOLS,
        temperature=temperature,
    )

    contents: list[types.Content] = [
        types.Content(role="user", parts=[types.Part.from_text(text=prompt)])
    ]

    _retries = 2
    result = None

    for _iteration in range(max_tool_calls + 1):
        last_exc: Exception | None = None
        for attempt in range(_retries + 1):
            try:
                result = client.models.generate_content(
                    model=settings.gemini_model,
                    contents=contents,
                    config=config,
                )
                break
            except Exception as e:
                last_exc = e
                msg = str(e)
                is_transient = any(k in msg for k in ("503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED"))
                if is_transient and attempt < _retries:
                    wait = 2 ** attempt
                    logger.warning("Gemini tool-call 일시 오류 (재시도 %d/%d): %s", attempt + 1, _retries, msg[:120])
                    time.sleep(wait)
                    continue
                break
        if result is None:
            raise RuntimeError("AI 서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.") from last_exc

        candidate = result.candidates[0]
        fn_calls = [p for p in candidate.content.parts if _has_function_call(p)]

        if not fn_calls:
            return _safe_text(result)

        contents.append(candidate.content)

        for part in fn_calls:
            fn_name = part.function_call.name
            fn_args = dict(part.function_call.args or {})
            try:
                # Reference through module so the test patch on app.llm.gemini.execute_tool is respected
                fn_result = sys.modules[__name__].execute_tool(fn_name, fn_args, username or "")  # type: ignore[attr-defined]
            except Exception as e:
                fn_result = {"error": str(e)}
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(
                        name=fn_name,
                        response={"output": fn_result},
                    )],
                )
            )

    return _safe_text(result) if result else "답변을 생성할 수 없습니다."
