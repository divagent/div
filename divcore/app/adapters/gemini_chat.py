import logging

import httpx
from google.genai import types

from app.adapters.gemini import (
    _usable_models,
    get_cloudflare_creds,
    get_gemini_client,
    get_groq_client,
    get_mistral_client,
    get_nvidia_key,
    next_ai_model,
)

logger = logging.getLogger(__name__)


def _wants_json(system_prompt: str | None, messages: list | None) -> bool:
    text = system_prompt or ""
    if messages:
        text += "\n".join(str(m.get("content", "")) for m in messages)
    return "json" in text.lower()


def _gemini_contents(messages: list) -> tuple[str | None, list[types.Content]]:
    system_parts: list[str] = []
    contents: list[types.Content] = []

    for message in messages:
        role = message.get("role")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
            continue

        gemini_role = "model" if role == "assistant" else "user"
        contents.append(
            types.Content(
                role=gemini_role,
                parts=[types.Part.from_text(text=content)],
            )
        )

    return "\n\n".join(system_parts) if system_parts else None, contents


async def _call_gemini(model, system_instruction, contents, response_mime_type) -> str:
    resp = await get_gemini_client().aio.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type=response_mime_type,
            temperature=0.2,
        ),
    )
    text = resp.text
    if text:
        return text
    # No usable text. Do NOT return "" — that just trips the caller on an empty
    # parse with no clue why. Surface Gemini's actual reason (safety block,
    # MAX_TOKENS, recitation, ...) so the failure names itself.
    feedback = getattr(resp, "prompt_feedback", None)
    block = getattr(feedback, "block_reason", None)
    candidates = getattr(resp, "candidates", None) or []
    finish = getattr(candidates[0], "finish_reason", None) if candidates else None
    raise RuntimeError(
        f"Gemini {model} returned no text (finish_reason={finish}, block_reason={block})"
    )


async def _call_groq(model, messages, response_mime_type) -> str:
    client = get_groq_client()
    if client is None:
        raise RuntimeError("GROQ_API_KEY is not configured")
    kwargs = {
        "model": model,
        # messages are already role/content dicts (system/user/assistant) -- Groq
        # is OpenAI-compatible so they pass through unchanged.
        "messages": [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages],
        "temperature": 0.2,
    }
    if response_mime_type == "application/json":
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.completions.create(**kwargs)
    if not resp.choices:
        raise RuntimeError(f"Groq {model} returned no choices")
    content = resp.choices[0].message.content
    if not content:
        finish = getattr(resp.choices[0], "finish_reason", None)
        raise RuntimeError(f"Groq {model} returned empty content (finish_reason={finish})")
    return content


async def _call_mistral(model, messages, response_mime_type) -> str:
    client = get_mistral_client()
    if client is None:
        raise RuntimeError("MISTRAL_API_KEY is not configured")
    kwargs = {
        # messages are already role/content dicts (system/user/assistant); Mistral's
        # chat API takes the same shape, so they pass through unchanged.
        "model": model,
        "messages": [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages],
        "temperature": 0.2,
    }
    if response_mime_type == "application/json":
        kwargs["response_format"] = {"type": "json_object"}
    resp = await client.chat.complete_async(**kwargs)
    if not resp.choices:
        raise RuntimeError(f"Mistral {model} returned no choices")
    content = resp.choices[0].message.content
    if not content:
        finish = getattr(resp.choices[0], "finish_reason", None)
        raise RuntimeError(f"Mistral {model} returned empty content (finish_reason={finish})")
    return content


async def _openai_compatible_chat(url, token, model, messages, response_mime_type, *, who) -> str:
    """POST to any OpenAI-compatible /chat/completions endpoint (Cloudflare, NVIDIA)
    and return the message content. Raises with the real HTTP body / finish_reason
    on any failure rather than returning ""."""
    payload: dict = {
        "model": model,
        "messages": [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in messages],
        "temperature": 0.2,
    }
    if response_mime_type == "application/json":
        payload["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        r = await client.post(url, headers={"Authorization": f"Bearer {token}"}, json=payload)
    if r.status_code != 200:
        raise RuntimeError(f"{who} {model} HTTP {r.status_code}: {r.text[:500]}")
    choices = (r.json() or {}).get("choices") or []
    if not choices:
        raise RuntimeError(f"{who} {model} returned no choices: {r.text[:500]}")
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        finish = choices[0].get("finish_reason")
        raise RuntimeError(f"{who} {model} returned empty content (finish_reason={finish})")
    return content


async def _call_cloudflare(model, messages, response_mime_type) -> str:
    token, account = get_cloudflare_creds()
    if not (token and account):
        raise RuntimeError("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must both be set")
    # Cloudflare Workers AI exposes an OpenAI-compatible chat endpoint; the account id
    # is part of the URL, the model id (e.g. "@cf/meta/...") goes in the body.
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1/chat/completions"
    return await _openai_compatible_chat(url, token, model, messages, response_mime_type, who="Cloudflare")


async def _call_nvidia(model, messages, response_mime_type) -> str:
    token = get_nvidia_key()
    if not token:
        raise RuntimeError("NVIDIA_API_KEY is not configured")
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    return await _openai_compatible_chat(url, token, model, messages, response_mime_type, who="NVIDIA")


async def _invoke(provider, model_id, system_instruction, contents, messages, response_mime_type) -> str:
    """Call one model via its provider's client and return raw text output."""
    if provider == "gemini":
        return await _call_gemini(model_id, system_instruction, contents, response_mime_type)
    if provider == "groq":
        return await _call_groq(model_id, messages, response_mime_type)
    if provider == "mistral":
        return await _call_mistral(model_id, messages, response_mime_type)
    if provider == "cloudflare":
        return await _call_cloudflare(model_id, messages, response_mime_type)
    if provider == "nvidia":
        return await _call_nvidia(model_id, messages, response_mime_type)
    raise RuntimeError(f"Unknown AI provider: {provider}")


async def chat_completion_agent_with_model(
    system_prompt: str | list | None = None,
    user_prompt: str | None = None,
    messages: list | None = None,
    model: tuple[str, str] | None = None,
    *,
    on_attempt_error=None,
) -> tuple[str, str]:
    """Like chat_completion_agent, but also returns the "provider:model_id" label of
    the model that actually ran, so callers can tell the user exactly which model
    produced the output.

    Rotation with in-ring fallback: if the caller pins `model`, it is tried once.
    Otherwise we try each usable model in the ring ONCE (drawing the next via the
    shared cursor). On a failure -- a provider error, a 404/no-access model, or an
    empty response -- we log the cause, report it via `on_attempt_error(label, exc)`
    if given (so a trace can SHOW it), then rotate to the next model. The first
    success returns. If every model fails we raise the LAST error -- we never swallow
    it into "".

    `on_attempt_error` is an optional async callback invoked once per failed attempt.
    """
    if messages is None and isinstance(system_prompt, list):
        messages = system_prompt
        system_prompt = None

    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_prompt or ""},
        ]

    system_instruction, contents = _gemini_contents(messages)
    response_mime_type = "application/json" if _wants_json(str(system_prompt or ""), messages) else None

    # Pinned model => one shot; otherwise try each usable model in the ring once.
    attempts = 1 if model else max(1, len(_usable_models()))
    last_exc: Exception | None = None
    for _ in range(attempts):
        provider, model_id = model or next_ai_model()
        label = f"{provider}:{model_id}"
        try:
            text = await _invoke(provider, model_id, system_instruction, contents, messages, response_mime_type)
            return text, label
        except Exception as exc:
            # Surface the cause (log + optional callback), then rotate onward. We do
            # not eat it: if this was the last model, we re-raise below.
            logger.warning("AI %s failed, rotating to next model: %s", label, exc)
            last_exc = exc
            if on_attempt_error is not None:
                try:
                    await on_attempt_error(label, exc)
                except Exception:  # noqa: BLE001 - a broken reporter must not mask the real error
                    pass

    assert last_exc is not None  # attempts >= 1, so a failure path always set this
    raise last_exc


async def chat_completion_agent(
    system_prompt: str | list | None = None,
    user_prompt: str | None = None,
    messages: list | None = None,
    model: tuple[str, str] | None = None,
) -> str:
    """
    Gemini/Groq-backed chat helper.
    Supports both repo calling styles:
    - chat_completion_agent(system_prompt, user_prompt)
    - chat_completion_agent(messages=[...])
    """
    text, _ = await chat_completion_agent_with_model(system_prompt, user_prompt, messages, model)
    return text


# async def chat_completion(system_prompt: str, user_prompt: str) -> str:
#     resp = await client.chat.completions.create(
#         model=model_name,
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_prompt},
#         ],
#         temperature=0.2,
#     )
#     return resp.choices[0].message.content


# response = client.chat.completions.create(
#     messages=[
#         {
#             "role": "system",
#             "content": "You are a helpful assistant.",
#         },
#         {
#             "role": "user",
#             "content": "I am going to Paris, what should I see?",
#         }
#     ],
#     max_completion_tokens=16384,
#     model=deployment
# )

# print(response.choices[0].message.content)


