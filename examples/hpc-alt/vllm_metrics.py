#!/usr/bin/env python3
"""Sample a vLLM server's Prometheus /metrics every INTERVAL seconds into a CSV.

Used to pick a safe number of concurrent episodes per server: watch how
per-token decode latency, time-to-first-token, KV-cache usage and preemptions
move as running requests go up.

    python3 vllm_metrics.py http://localhost:8000 trial.csv [INTERVAL=10]

Each row is one interval. Counters and histograms are turned into per-interval
values (mean latency over the requests that finished in that interval).
"""
import csv, re, sys, time, urllib.request

BASE = sys.argv[1].rstrip("/").removesuffix("/v1")
OUT = sys.argv[2]
INTERVAL = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

LINE = re.compile(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eEinfNa]+)$')


def scrape() -> dict[str, float]:
    """Sum every series of each metric name (all labels collapsed)."""
    text = urllib.request.urlopen(f"{BASE}/metrics", timeout=10).read().decode()
    out: dict[str, float] = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if m and not line.startswith("#"):
            out[m.group(1)] = out.get(m.group(1), 0.0) + float(m.group(3))
    return out


def pick(d: dict, *names: str) -> float | None:
    """First metric present among several names (they vary across vLLM versions)."""
    for n in names:
        if n in d:
            return d[n]
    return None


def hist_mean(cur, prev, name):
    s, c = f"{name}_sum", f"{name}_count"
    if s not in cur or c not in cur:
        return None
    dc = cur[c] - prev.get(c, 0.0)
    return (cur[s] - prev.get(s, 0.0)) / dc if dc > 0 else None


def delta(cur, prev, *names):
    for n in names:
        if n in cur:
            return cur[n] - prev.get(n, 0.0)
    return None


FIELDS = ["time", "running", "waiting", "kv_usage_pct", "preemptions",
          "finished", "e2e_s", "ttft_s", "tpot_ms", "prefill_tok_s", "decode_tok_s",
          "prefix_hit_pct"]

prev, t_prev = scrape(), time.time()
with open(OUT, "a", newline="") as fh:
    w = csv.writer(fh)
    if fh.tell() == 0:
        w.writerow(FIELDS)
    print(" ".join(f"{f:>10s}" for f in FIELDS[1:]), flush=True)
    while True:
        time.sleep(INTERVAL)
        try:
            cur, now = scrape(), time.time()
        except Exception as e:  # noqa: BLE001 -- keep sampling through blips
            print(f"scrape failed: {e}", flush=True)
            continue
        dt = now - t_prev
        kv = pick(cur, "vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc")
        tpot = hist_mean(cur, prev, "vllm:time_per_output_token_seconds") \
            or hist_mean(cur, prev, "vllm:inter_token_latency_seconds")
        hits = delta(cur, prev, "vllm:prefix_cache_hits_total", "vllm:gpu_prefix_cache_hits_total")
        qs = delta(cur, prev, "vllm:prefix_cache_queries_total", "vllm:gpu_prefix_cache_queries_total")
        pt = delta(cur, prev, "vllm:prompt_tokens_total")
        gt = delta(cur, prev, "vllm:generation_tokens_total")
        row = {
            "time": time.strftime("%H:%M:%S"),
            "running": pick(cur, "vllm:num_requests_running"),
            "waiting": pick(cur, "vllm:num_requests_waiting"),
            "kv_usage_pct": None if kv is None else 100 * kv,
            "preemptions": delta(cur, prev, "vllm:num_preemptions_total"),
            "finished": delta(cur, prev, "vllm:e2e_request_latency_seconds_count"),
            "e2e_s": hist_mean(cur, prev, "vllm:e2e_request_latency_seconds"),
            "ttft_s": hist_mean(cur, prev, "vllm:time_to_first_token_seconds"),
            "tpot_ms": None if tpot is None else 1000 * tpot,
            "prefill_tok_s": None if pt is None else pt / dt,
            "decode_tok_s": None if gt is None else gt / dt,
            "prefix_hit_pct": None if not qs else 100 * hits / qs,
        }
        vals = ["" if row[f] is None else (row[f] if f == "time" else round(row[f], 2))
                for f in FIELDS]
        w.writerow(vals)
        fh.flush()
        print(" ".join(f"{str(v):>10s}" for v in vals[1:]), flush=True)
        prev, t_prev = cur, now
