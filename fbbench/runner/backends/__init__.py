"""Backend factory: model id -> a provider Backend instance."""
from __future__ import annotations

import os

from fbbench.models import OPENAI_COMPAT, provider_for

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
    if provider == "ollama":
        # Local open models (Ollama/vLLM) over an OpenAI-compatible endpoint.
        # Keyless: point at OLLAMA_BASE_URL and force the small-model local path.
        from .openai_backend import OpenAIBackend
        base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        return OpenAIBackend(model, api_key=api_key or "ollama",
                             base_url=base, local=True)
    if provider in OPENAI_COMPAT:
        # DeepSeek / DashScope (Qwen) / Moonshot (Kimi) / Zhipu (GLM) /
        # OpenRouter all speak the OpenAI chat-completions protocol; reuse that
        # backend pointed at the provider's endpoint with its own key.
        from .openai_backend import OpenAIBackend
        base_env, base_default, key_env = OPENAI_COMPAT[provider]
        base = os.environ.get(base_env, base_default)
        return OpenAIBackend(model, api_key=api_key, base_url=base, key_env=key_env)
    raise ValueError(f"unknown provider for model {model!r}")
