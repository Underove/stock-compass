import json
import logging
import time
from functools import lru_cache

from openai import OpenAI

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_client() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY가 .env에 설정되지 않았습니다")
    return OpenAI(api_key=settings.openai_api_key, timeout=90)


def generate_answer(
    prompt: str,
    system_instruction: str | None = None,
    temperature: float = 0.3,
    _retries: int = 2,
    model: str | None = None,
) -> str:
    client = get_client()
    _model = model or settings.openai_model
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    last_exc: Exception | None = None
    for attempt in range(_retries + 1):
        try:
            response = client.chat.completions.create(
                model=_model,
                messages=messages,
                temperature=temperature,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            last_exc = e
            msg = str(e)
            is_transient = any(k in msg for k in ("503", "429", "rate_limit", "overloaded"))
            if is_transient and attempt < _retries:
                wait = 2 ** attempt
                logger.warning("OpenAI 일시 오류 (재시도 %d/%d): %s", attempt + 1, _retries, msg[:120])
                time.sleep(wait)
                continue
            break
    raise RuntimeError("AI 서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.") from last_exc


def generate_with_tools(
    prompt: str,
    system_instruction: str | None = None,
    username: str | None = None,
    temperature: float = 0.3,
    max_tool_calls: int = 3,
    model: str | None = None,
) -> str:
    from app.tools import OPENAI_TOOLS, execute_tool

    client = get_client()
    _model = model or settings.openai_model
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    _retries = 2
    response = None

    for _iteration in range(max_tool_calls + 1):
        last_exc: Exception | None = None
        for attempt in range(_retries + 1):
            try:
                response = client.chat.completions.create(
                    model=_model,
                    messages=messages,
                    tools=OPENAI_TOOLS,
                    temperature=temperature,
                )
                break
            except Exception as e:
                last_exc = e
                msg = str(e)
                is_transient = any(k in msg for k in ("503", "429", "rate_limit", "overloaded"))
                if is_transient and attempt < _retries:
                    wait = 2 ** attempt
                    logger.warning("OpenAI tool-call 일시 오류 (재시도 %d/%d): %s", attempt + 1, _retries, msg[:120])
                    time.sleep(wait)
                    continue
                break

        if response is None:
            raise RuntimeError("AI 서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.") from last_exc

        choice = response.choices[0]

        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            return (choice.message.content or "").strip()

        messages.append(choice.message)

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}
            try:
                fn_result = execute_tool(fn_name, fn_args, username or "")
            except Exception as e:
                fn_result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(fn_result, ensure_ascii=False),
            })

    if response:
        return (response.choices[0].message.content or "").strip()
    return "답변을 생성할 수 없습니다."
