"""Model response latency: one number per model call, summarized per episode
and pooled across a sweep.

A call's latency is the wall-clock time `backend.complete()` took, measured on
the runner. For a self-hosted model that is the server's queueing + prefill +
decode time plus the tunnel; for an API model it also includes the network. It
is what decides how many turns fit in an episode's clock, and it is the figure
to watch when several episodes share one server.

Per call the episode records `latency_s` and `output_tok_per_s` on its
`assistant` event; per episode `score.json` carries `latency` (from
`summarize`); a sweep pools every call of a model (`pool`).
"""
from __future__ import annotations

import statistics


def _pct(sorted_xs: list[float], p: float) -> float:
    """Nearest-rank percentile of an already sorted, non-empty list."""
    k = max(0, min(len(sorted_xs) - 1, int(round(p / 100 * len(sorted_xs) + 0.5)) - 1))
    return sorted_xs[k]


def summarize(per_call_s: list[float], *, output_tokens: int = 0,
              duration_s: float = 0.0) -> dict:
    """Latency summary of one episode (or of a pooled set of calls)."""
    xs = sorted(x for x in per_call_s if x is not None and x >= 0)
    total = sum(xs)
    out: dict = {"model_calls": len(xs), "model_time_s": round(total, 2)}
    if xs:
        out.update({
            "mean_s": round(statistics.fmean(xs), 2),
            "p50_s": round(_pct(xs, 50), 2),
            "p90_s": round(_pct(xs, 90), 2),
            "p99_s": round(_pct(xs, 99), 2),
            "max_s": round(xs[-1], 2),
        })
    if output_tokens:
        out["output_tokens"] = int(output_tokens)
    if total > 0 and output_tokens:
        out["output_tok_per_s"] = round(output_tokens / total, 1)
    if duration_s > 0:
        # Share of the episode spent waiting on the model; the rest is tools,
        # grading and the runner itself.
        out["model_time_frac"] = round(total / duration_s, 3)
    out["per_call_s"] = [round(x, 2) for x in per_call_s if x is not None and x >= 0]
    return out


def pool(scores: list[dict]) -> dict:
    """Pool the per-call latencies of several score.json records (one model)."""
    calls: list[float] = []
    out_tok = 0
    duration = 0.0
    for s in scores:
        lat = s.get("latency") or {}
        calls.extend(lat.get("per_call_s") or [])
        out_tok += int(lat.get("output_tokens") or 0)
        duration += float(s.get("duration_s") or 0.0)
    pooled = summarize(calls, output_tokens=out_tok, duration_s=duration)
    pooled.pop("per_call_s", None)
    return pooled
