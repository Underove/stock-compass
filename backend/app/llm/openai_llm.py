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
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> str:
    client = get_client()
    _model = model or settings.openai_model
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    kwargs: dict = {"model": _model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        # gpt-5.x reasoning 모델은 max_completion_tokens 사용
        kwargs["max_completion_tokens"] = max_tokens
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_exc: Exception | None = None
    for attempt in range(_retries + 1):
        try:
            response = client.chat.completions.create(**kwargs)
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


def generate_with_tools_stream(
    prompt: str,
    system_instruction: str | None = None,
    username: str | None = None,
    temperature: float = 0.3,
    max_tool_calls: int = 3,
    model: str | None = None,
):
    """Function Calling 루프를 돌면서 최종 답변 토큰을 스트리밍.

    제너레이터로 ('token' | 'done' | 'error', data) 튜플을 yield.
    - token: 생성된 텍스트 조각 (str)
    - done: 완성된 전체 답변 (str)
    - error: 에러 메시지 (str)
    """
    from app.tools import OPENAI_TOOLS, execute_tool

    client = get_client()
    _model = model or settings.openai_model
    messages: list[dict] = []
    if system_instruction:
        messages.append({"role": "system", "content": system_instruction})
    messages.append({"role": "user", "content": prompt})

    full_answer = ""

    for _iteration in range(max_tool_calls + 1):
        try:
            stream = client.chat.completions.create(
                model=_model,
                messages=messages,
                tools=OPENAI_TOOLS,
                temperature=temperature,
                stream=True,
            )
        except Exception as e:
            logger.warning("OpenAI stream 호출 실패: %s", str(e)[:120])
            yield ("error", "AI 서버에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요.")
            return

        accumulated_tool_calls: dict[int, dict] = {}
        content_buffer = ""
        finish_reason: str | None = None

        for chunk in stream:
            if not chunk.choices:
                continue
            choice = chunk.choices[0]
            delta = choice.delta

            if delta.content:
                content_buffer += delta.content
                full_answer += delta.content
                yield ("token", delta.content)

            if delta.tool_calls:
                for tc in delta.tool_calls:
                    idx = tc.index
                    if idx not in accumulated_tool_calls:
                        accumulated_tool_calls[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc.id:
                        accumulated_tool_calls[idx]["id"] = tc.id
                    if tc.function:
                        if tc.function.name:
                            accumulated_tool_calls[idx]["name"] = tc.function.name
                        if tc.function.arguments:
                            accumulated_tool_calls[idx]["arguments"] += tc.function.arguments

            if choice.finish_reason:
                finish_reason = choice.finish_reason

        if finish_reason != "tool_calls" or not accumulated_tool_calls:
            yield ("done", full_answer)
            return

        tool_calls_list = [
            {
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            }
            for tc in accumulated_tool_calls.values()
        ]
        messages.append({
            "role": "assistant",
            "content": content_buffer or None,
            "tool_calls": tool_calls_list,
        })

        for tc in accumulated_tool_calls.values():
            try:
                fn_args = json.loads(tc["arguments"]) if tc["arguments"] else {}
            except json.JSONDecodeError:
                fn_args = {}
            try:
                fn_result = execute_tool(tc["name"], fn_args, username or "")
            except Exception as e:
                fn_result = {"error": str(e)}
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(fn_result, ensure_ascii=False),
            })

    yield ("done", full_answer)
