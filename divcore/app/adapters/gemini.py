import itertools
import os
from functools import lru_cache

from google import genai

from app.config import get_settings_singleton


DEFAULT_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


@lru_cache(maxsize=1)
def get_gemini_client() -> genai.Client:
    # Prod sets a real env var; locally fall back to the .env-backed settings so
    # dev and deployment behave the same.
    key = os.getenv("GEMINI_API_KEY") or get_settings_singleton().GEMINI_API_KEY
    return genai.Client(api_key=key)


@lru_cache(maxsize=1)
def get_groq_client():
    """Lazily build the Groq client. Returns None when no key is configured."""
    key = os.getenv("GROQ_API_KEY") or get_settings_singleton().GROQ_API_KEY
    if not key:
        return None
    from groq import AsyncGroq  # imported lazily so the app runs without groq installed

    return AsyncGroq(api_key=key)


@lru_cache(maxsize=1)
def get_mistral_client():
    """Lazily build the Mistral client. Returns None when no key is configured."""
    key = os.getenv("MISTRAL_API_KEY") or get_settings_singleton().MISTRAL_API_KEY
    if not key:
        return None
    from mistralai import Mistral  # imported lazily so the app runs without mistralai installed

    return Mistral(api_key=key)


# ===========================================================================
# Model rotation (hard round-robin)
# ===========================================================================
# Every LLM call takes the NEXT model from AI_MODELS and advances one shared,
# GLOBAL cursor -- so two consecutive calls, anywhere in the app, never hit the
# same model. There is NO in-call fallback and NO retry: a model that errors or
# returns nothing is already "spent", so the *next* call just uses the next model.
#
# To grow the rotation edit settings.AI_ROTATION_MODELS -- "provider:model_id"
# entries; nothing else changes. To support a new provider, add its key mapping
# below and a branch in gemini_chat._invoke().
_PROVIDER_KEYS = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cloudflare": "CLOUDFLARE_API_TOKEN",
    "nvidia": "NVIDIA_API_KEY",
}


def get_nvidia_key():
    """NVIDIA NIM API key from env or settings, or None."""
    return os.getenv("NVIDIA_API_KEY") or get_settings_singleton().NVIDIA_API_KEY


def get_cloudflare_creds() -> tuple:
    """(api_token, account_id) for Cloudflare Workers AI, or (None, None) if either
    is missing. Both are required — the account id is part of the request URL."""
    settings = get_settings_singleton()
    token = os.getenv("CLOUDFLARE_API_TOKEN") or settings.CLOUDFLARE_API_TOKEN
    account = os.getenv("CLOUDFLARE_ACCOUNT_ID") or settings.CLOUDFLARE_ACCOUNT_ID
    if token and account:
        return token, account
    return None, None

_cursor = itertools.count()


def _parse_models(specs):
    """Parse "provider:model_id" strings into (provider, model_id) pairs, skipping
    blanks and unknown providers."""
    models = []
    for spec in specs or []:
        provider, _, model_id = spec.partition(":")
        provider, model_id = provider.strip().lower(), model_id.strip()
        if provider in _PROVIDER_KEYS and model_id:
            models.append((provider, model_id))
    return models


# The rotation ring, from config (with a back-compat default if it's unset).
AI_MODELS = _parse_models(getattr(get_settings_singleton(), "AI_ROTATION_MODELS", None)) or [
    ("gemini", DEFAULT_GEMINI_MODEL),
]


def _model_configured(provider: str) -> bool:
    settings = get_settings_singleton()
    attr = _PROVIDER_KEYS.get(provider)
    # Gemini also honours the OS env var used by get_gemini_client().
    if provider == "gemini" and os.getenv("GEMINI_API_KEY"):
        return True
    if provider == "groq" and os.getenv("GROQ_API_KEY"):
        return True
    if provider == "mistral" and os.getenv("MISTRAL_API_KEY"):
        return True
    if provider == "cloudflare":
        # Needs BOTH token and account id, from env or settings.
        return all(get_cloudflare_creds())
    if provider == "nvidia" and os.getenv("NVIDIA_API_KEY"):
        return True
    return bool(attr and getattr(settings, attr, None))


def _usable_models():
    """The rotation ring limited to models whose provider has an API key set."""
    return [m for m in AI_MODELS if _model_configured(m[0])]


def next_ai_model():
    """Hard-rotate: return the next (provider, model_id) and advance the GLOBAL
    cursor so the very next LLM call -- anywhere in the app -- uses a different model.

    Call this exactly ONCE per LLM invocation (the cursor advances whether or not the
    model then succeeds -- a spent model is not retried). Raises RuntimeError if
    nothing is configured.
    """
    usable = _usable_models()
    if not usable:
        raise RuntimeError("No AI model configured (set GEMINI_API_KEY and/or GROQ_API_KEY)")
    return usable[next(_cursor) % len(usable)]
