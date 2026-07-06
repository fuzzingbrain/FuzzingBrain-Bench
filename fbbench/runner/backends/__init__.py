"""Backend factory: model id -> a provider Backend instance."""
from __future__ import annotations

import os

from fbbench.models import provider_for

from .base import Backend  # noqa: F401


def make_backend(model: str, api_key: str | None = None) -> Backend:
    provider = provider_for(model)
    if provider == "anthropic":
        from .anthropic_backend import AnthropicBackend
        return AnthropicBackend(model, api_key=api_key)
    if provider == "openai":
        from .openai_backend import OpenAIBackend
        return OpenAIBackend(model, api_key=api_key)
    if provider == "gemini":
        from .gemini_backend import GeminiBackend
        return GeminiBackend(model, api_key=api_key)
    if provider == "deepseek":
        # DeepSeek speaks the OpenAI chat-completions protocol; reuse that
        # backend pointed at DeepSeek's endpoint with its own key.
        from .openai_backend import OpenAIBackend
        base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        return OpenAIBackend(model, api_key=api_key, base_url=base,
                             key_env="DEEPSEEK_API_KEY")
    raise ValueError(f"unknown provider for model {model!r}")
