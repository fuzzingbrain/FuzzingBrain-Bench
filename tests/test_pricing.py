"""The Anthropic price table, pinned to the published list prices.

Verified 2026-09-16 against https://platform.claude.com/docs/en/about-claude/pricing.
These are the numbers every arm's cost is computed from, so a stale entry does
not fail anything -- it quietly reports the wrong amount of money, in a report
someone then puts in a paper.

Per-million-token rates, straight off that page:

    model              input   5m write   cache hit   output
    Claude Opus 5      $5      $6.25      $0.50       $25
    Claude Opus 4.8    $5      $6.25      $0.50       $25
    Claude Sonnet 5    $2      $2.50      $0.20       $10
    Claude Sonnet 4.6  $3      $3.75      $0.30       $15
    Claude Haiku 4.5   $1      $1.25      $0.10       $5
    Claude Fable 5.1   $10     $12.50     $0.25       $50   <- 0.025x read
"""

import pytest

from fbbench.models.pricing import cost_usd

M = 1_000_000

# (model, input, 5m cache write, cache hit, output) per MTok, as published.
PUBLISHED = [
    ("claude-opus-5",     5.0,  6.25, 0.50, 25.0),
    ("claude-opus-4-8",   5.0,  6.25, 0.50, 25.0),
    ("claude-opus-4-7",   5.0,  6.25, 0.50, 25.0),
    ("claude-sonnet-5",   2.0,  2.50, 0.20, 10.0),
    ("claude-sonnet-4-6", 3.0,  3.75, 0.30, 15.0),
    ("claude-haiku-4-5",  1.0,  1.25, 0.10,  5.0),
    ("claude-fable-5-1", 10.0, 12.50, 0.25, 50.0),
]


@pytest.mark.parametrize(("model", "inp", "write", "read", "out"), PUBLISHED)
def test_every_bucket_matches_the_published_rate(model, inp, write, read, out):
    r = cost_usd(model, M, M, M, M)
    assert r["pricing_known"]
    assert r["input_usd"] == pytest.approx(inp)
    assert r["cache_write_usd"] == pytest.approx(write)
    assert r["cache_read_usd"] == pytest.approx(read)
    assert r["output_usd"] == pytest.approx(out)


def test_fable_51_reads_cache_at_a_quarter_of_the_usual_rate():
    # The one Claude model that does not use the 0.1x read multiplier. A
    # per-provider constant cannot express it, and on a cached agent run the
    # cache reads ARE the bill -- 98% of fbagent's input tokens were reads.
    assert cost_usd("claude-fable-5-1", 0, 0, M, 0)["cache_read_usd"] == pytest.approx(0.25)
    assert cost_usd("claude-fable-5", 0, 0, M, 0)["cache_read_usd"] == pytest.approx(1.00)


def test_a_realistic_cached_opus_5_run():
    # The shape an fb-agent run actually has: almost all input from cache.
    r = cost_usd("claude-opus-5", input_tokens=35_217, output_tokens=6_376,
                 cache_read_tokens=537_296, cache_write_tokens=29_186)
    expected = (35_217 * 5 + 6_376 * 25 + 537_296 * 0.5 + 29_186 * 6.25) / M
    # cost_usd rounds its total to 6dp, so compare at that resolution.
    assert r["total_usd"] == pytest.approx(expected, abs=1e-6)
    assert r["total_usd"] == 0.786546


def test_an_unknown_model_is_unpriced_rather_than_free():
    r = cost_usd("claude-opus-9", M, M)
    assert r["pricing_known"] is False
    assert r["total_usd"] is None
