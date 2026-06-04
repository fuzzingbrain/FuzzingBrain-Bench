"""Per-model API pricing -> USD cost for an episode.

Rates are USD per 1,000,000 tokens (standard tier, <=200k context where
providers tier by context length), sourced from public list prices as of
May 2026. EDIT FREELY — prices change; verify against the provider before
quoting these numbers.

cost_usd() prices prompt-caching correctly when the backend reports cache
buckets: fresh input at 1x, cache WRITE at the provider's write multiplier,
cache READ at the provider's (much cheaper) read multiplier. Reasoning/thinking
tokens are billed as output and are included. Batch discounts are not modeled.
"""
from __future__ import annotations

from fbbench.models.catalog import provider_for

# Per-provider prompt-cache multipliers, applied to the INPUT rate.
#   read  = cache hit  (re-reading an already-cached prefix)
#   write = cache create (the first turn a prefix is cached; a one-time surcharge
#           on the newly-written tokens; providers that auto-cache have none)
# Anthropic: documented 0.1x read / 1.25x write. OpenAI auto-caches with a ~0.1x
# read and no write surcharge. Gemini implicit cache ~0.25x read. EDIT to match
# the provider's current published cache pricing.
CACHE_READ_MULT = {"anthropic": 0.10, "openai": 0.10, "gemini": 0.25}
CACHE_WRITE_MULT = {"anthropic": 1.25, "openai": 1.0, "gemini": 1.0}

# model_id -> (input_usd_per_mtok, output_usd_per_mtok)
PRICES: dict[str, tuple[float, float]] = {
    # Anthropic
    "claude-opus-4-7":   (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5":  (1.0, 5.0),
    # OpenAI
    "gpt-5.5":      (5.0, 30.0),
    "gpt-5.4":      (2.5, 15.0),
    "gpt-5.4-mini": (0.75, 4.5),
    "gpt-5":        (1.25, 10.0),
    # Gemini  (3.1 Pro priced at the Gemini-3 Pro tier; estimate)
    "gemini-3.1-pro-preview": (2.0, 12.0),
    "gemini-3-pro-preview":   (2.0, 12.0),
    "gemini-3.5-flash":       (1.5, 9.0),
    "gemini-2.5-pro":         (1.25, 10.0),
    "gemini-2.5-flash":       (0.30, 2.5),
    "gemini-2.5-flash-lite":  (0.10, 0.40),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int,
             cache_read_tokens: int = 0, cache_write_tokens: int = 0) -> dict:
    """Return a cost breakdown. total_usd is None when the model is unpriced.

    input_tokens is FRESH (uncached) input. cache_read/write_tokens are the
    cache-hit / cache-create buckets, priced at the provider's cache multipliers
    of the input rate. Backends that do not report caching pass 0 for both, so
    this reduces to the old flat-rate behavior.
    """
    rates = PRICES.get(model)
    if rates is None:
        return {"input_tokens": input_tokens, "output_tokens": output_tokens,
                "cache_read_tokens": cache_read_tokens,
                "cache_write_tokens": cache_write_tokens,
                "pricing_known": False, "total_usd": None,
                "note": f"no price for {model!r} in pricing.py — edit to add"}
    in_rate, out_rate = rates
    provider = provider_for(model)
    read_mult = CACHE_READ_MULT.get(provider, 0.10)
    write_mult = CACHE_WRITE_MULT.get(provider, 1.0)
    in_usd = input_tokens / 1e6 * in_rate
    read_usd = cache_read_tokens / 1e6 * in_rate * read_mult
    write_usd = cache_write_tokens / 1e6 * in_rate * write_mult
    out_usd = output_tokens / 1e6 * out_rate
    total = in_usd + read_usd + write_usd + out_usd
    return {
        "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "pricing_known": True,
        "input_usd_per_mtok": in_rate, "output_usd_per_mtok": out_rate,
        "cache_read_mult": read_mult, "cache_write_mult": write_mult,
        "input_usd": round(in_usd, 6),
        "cache_read_usd": round(read_usd, 6),
        "cache_write_usd": round(write_usd, 6),
        "output_usd": round(out_usd, 6),
        "total_usd": round(total, 6),
    }
