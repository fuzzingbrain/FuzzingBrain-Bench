"""Provider-neutral backend contract for the FuzzingBrain Bench runner.

The episode loop (runner/episode.py) is written against these types only; each
provider adapter (anthropic/openai/gemini) translates the neutral conversation
history + tool schemas to its own SDK and parses tool calls back out.

Neutral message history is a list of dicts in one of three shapes:
  {"role": "user",      "content": <str>}
  {"role": "assistant", "text": <str>, "tool_calls": [ToolCall, ...]}
  {"role": "tool",      "results": [ToolResult, ...]}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict
    # provider-opaque metadata that must round-trip in history
    # (e.g. Gemini 3 thought_signature on function_call parts)
    meta: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    id: str          # matches the originating ToolCall.id
    name: str
    content: str     # JSON-encoded tool output
    is_error: bool = False


@dataclass
class Completion:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = ""        # normalized: "tool_use" | "end" | other SDK value
    # Token buckets, normalized across providers so cost_usd can price each at
    # its own rate. input_tokens is FRESH (uncached) input billed at 1x; the
    # two cache buckets are billed at the provider's cache multipliers.
    #   Anthropic: input=usage.input_tokens (already excludes cache),
    #              cache_write=cache_creation_input_tokens (1.25x),
    #              cache_read=cache_read_input_tokens (0.1x).
    #   OpenAI:    prompt_tokens INCLUDES cache, so input=prompt-cached,
    #              cache_read=prompt_tokens_details.cached_tokens, write=0.
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0


class Backend(Protocol):
    """One LLM provider. Stateless across calls; the loop owns the history."""

    model: str

    def complete(
        self,
        system: str,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int,
    ) -> Completion:
        ...
