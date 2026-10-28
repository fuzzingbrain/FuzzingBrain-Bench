"""OpenAI backend: neutral history <-> chat.completions tool calls.

Handles the gpt-5.x / o-series reasoning models, which require
`max_completion_tokens` (not `max_tokens`) and reject a custom temperature.
"""
from __future__ import annotations

import copy
import json
import os

import openai

from .base import Completion, ToolCall


def _is_reasoning(model: str) -> bool:
    m = model.lower()
    return m.startswith(("gpt-5", "o1", "o3", "o4"))


def _is_local(model: str) -> bool:
    # Open models served via an OpenAI-compatible local endpoint (Ollama/vLLM).
    return model.lower().startswith(("llama", "codellama", "ollama"))


# Self-hosted models run with the sampling FB-Agent sends them
# (FuzzingBrain-Agent config/hprc_gemma.yaml: Gemma's model card, thinking on)
# and no output cap, as FB-Agent sends none, so the two arms make the same
# request to the same server.
OPEN_MODEL_SAMPLING = {
    "gemma4:31b-qat": {
        "temperature": 1.0,
        "top_p": 0.95,
        "extra_body": {"top_k": 64,
                       "chat_template_kwargs": {"enable_thinking": True}},
    },
    # Qwen3.8 thinks by default (no enable_thinking needed), per its model card;
    # mirrors FuzzingBrain-Agent config/hprc_qwen.yaml (temp 1.0, top_p 0.95, top_k 20).
    "qwen3.8:27b": {
        "temperature": 1.0,
        "top_p": 0.95,
        "extra_body": {"top_k": 20},
    },
    # Qwen3.8-Flash-Next (MoE). Same Qwen sampling convention; the model id must
    # match vLLM's --served-model-name and the --model passed to the run.
    "qwen3.8-flash-next:fp8": {
        "temperature": 1.0,
        "top_p": 0.95,
        "extra_body": {"top_k": 20},
    },
}


class OpenAIBackend:
    def __init__(self, model: str, api_key: str | None = None,
                 base_url: str | None = None, key_env: str = "OPENAI_API_KEY",
                 local: bool = False):
        # base_url/key_env let this backend serve any OpenAI-compatible provider
        # (e.g. DeepSeek at https://api.deepseek.com with DEEPSEEK_API_KEY).
        # local=True forces the small-model path (Ollama/vLLM); it is also
        # inferred from a llama*-style id. A globally-set OLLAMA_BASE_URL only
        # flips to local when no explicit base_url is given, so a cloud provider
        # that passes its own base_url is never hijacked by that env var.
        self.model = model
        self.local = local or _is_local(model)
        if not base_url and os.environ.get("OLLAMA_BASE_URL"):
            self.local = True
        # max_retries above the SDK default (2) for rate-limit resilience.
        if self.local:
            base = base_url or os.environ.get(
                "OLLAMA_BASE_URL", "http://localhost:11434/v1")
            # Ollama ignores the key but the SDK requires a non-empty string.
            self._client = openai.OpenAI(
                base_url=base, api_key=api_key or "ollama", max_retries=8)
        elif base_url:
            self._client = openai.OpenAI(
                base_url=base_url, api_key=api_key or os.environ.get(key_env),
                max_retries=8)
        else:
            self._client = openai.OpenAI(
                api_key=api_key or os.environ.get(key_env), max_retries=8)

    def _to_messages(self, system: str, messages: list[dict]) -> list[dict]:
        out: list[dict] = [{"role": "system", "content": system}]
        for m in messages:
            if m["role"] == "user":
                out.append({"role": "user", "content": m["content"]})
            elif m["role"] == "assistant":
                msg: dict = {"role": "assistant", "content": m.get("text") or None}
                tcs = m.get("tool_calls", [])
                if tcs:
                    msg["tool_calls"] = [{
                        "id": tc.id, "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                    } for tc in tcs]
                out.append(msg)
            elif m["role"] == "tool":
                for r in m["results"]:
                    out.append({"role": "tool", "tool_call_id": r.id, "content": r.content})
                # Budget note as a user message right after the tool outputs.
                if m.get("note"):
                    out.append({"role": "user", "content": m["note"]})
        return out

    def complete(self, system, messages, tools, max_tokens) -> Completion:
        api_tools = [{"type": "function", "function": {
            "name": t["name"], "description": t["description"],
            "parameters": t["input_schema"]}} for t in tools]
        kwargs: dict = {
            "model": self.model,
            "messages": self._to_messages(system, messages),
            "tools": api_tools,
        }
        if self.model in OPEN_MODEL_SAMPLING:
            kwargs.update(copy.deepcopy(OPEN_MODEL_SAMPLING[self.model]))
        elif _is_reasoning(self.model):
            # Reasoning tokens count against the completion budget; give room.
            kwargs["max_completion_tokens"] = max(max_tokens, 16384)
        elif self.local:
            # Local open models (Ollama): a 65k output cap is nonsensical for an
            # 8B and the default 8k context overflows fast on long episodes.
            # Cap the reply and request a larger KV context window.
            kwargs["max_tokens"] = min(max_tokens, 4096)
            kwargs["temperature"] = 1.0
            kwargs["extra_body"] = {"options": {"num_ctx": 32768}}
        else:
            kwargs["max_tokens"] = max_tokens
            kwargs["temperature"] = 1.0
        resp = self._client.chat.completions.create(**kwargs)

        msg = resp.choices[0].message
        c = Completion(text=msg.content or "",
                       stop_reason=resp.choices[0].finish_reason or "")
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            c.tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, input=args))
        if resp.usage:
            # OpenAI auto-caches server-side; prompt_tokens INCLUDES the cached
            # prefix, broken out under prompt_tokens_details.cached_tokens. Split
            # it so cost_usd prices the cached part at the cheaper read rate.
            prompt = resp.usage.prompt_tokens or 0
            details = getattr(resp.usage, "prompt_tokens_details", None)
            cached = (getattr(details, "cached_tokens", 0) or 0) if details else 0
            # DeepSeek reports cache hits under a different field name.
            if not cached:
                cached = getattr(resp.usage, "prompt_cache_hit_tokens", 0) or 0
            c.input_tokens = max(0, prompt - cached)
            c.cache_read_tokens = cached
            c.output_tokens = resp.usage.completion_tokens or 0
        return c
