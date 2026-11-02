#!/usr/bin/env python3
"""Sample a vLLM server's Prometheus metrics into a CSV file."""
import csv
import re
import sys
import time
import urllib.request

BASE = sys.argv[1].rstrip("/").removesuffix("/v1")
OUT = sys.argv[2]
INTERVAL = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+0-9.eEinfNa]+)$")


def scrape() -> dict[str, float]:
    text = urllib.request.urlopen(f"{BASE}/metrics", timeout=10).read().decode()
    out: dict[str, float] = {}
    for line in text.splitlines():
        match = LINE.match(line)
        if match and not line.startswith("#"):
            out[match.group(1)] = out.get(match.group(1), 0.0) + float(match.group(3))
    return out


def pick(values: dict[str, float], *names: str) -> float | None:
    for name in names:
        if name in values:
            return values[name]
    return None


def hist_mean(current, previous, name):
    total, count = f"{name}_sum", f"{name}_count"
    if total not in current or count not in current:
        return None
    delta_count = current[count] - previous.get(count, 0.0)
    if delta_count <= 0:
        return None
    return (current[total] - previous.get(total, 0.0)) / delta_count


def delta(current, previous, *names):
    for name in names:
        if name in current:
            return current[name] - previous.get(name, 0.0)
    return None


FIELDS = [
    "time", "running", "waiting", "kv_usage_pct", "preemptions", "finished",
    "e2e_s", "ttft_s", "tpot_ms", "prefill_tok_s", "decode_tok_s",
    "prefix_hit_pct",
]

previous, previous_time = scrape(), time.time()
with open(OUT, "a", newline="") as output_file:
    writer = csv.writer(output_file)
    if output_file.tell() == 0:
        writer.writerow(FIELDS)
    while True:
        time.sleep(INTERVAL)
        try:
            current, now = scrape(), time.time()
        except Exception as error:  # keep sampling through temporary tunnel blips
            print(f"scrape failed: {error}", flush=True)
            continue
        duration = now - previous_time
        kv = pick(current, "vllm:kv_cache_usage_perc", "vllm:gpu_cache_usage_perc")
        tpot = hist_mean(current, previous, "vllm:time_per_output_token_seconds")
        if tpot is None:
            tpot = hist_mean(current, previous, "vllm:inter_token_latency_seconds")
        hits = delta(current, previous, "vllm:prefix_cache_hits_total", "vllm:gpu_prefix_cache_hits_total")
        queries = delta(current, previous, "vllm:prefix_cache_queries_total", "vllm:gpu_prefix_cache_queries_total")
        prompt_tokens = delta(current, previous, "vllm:prompt_tokens_total")
        output_tokens = delta(current, previous, "vllm:generation_tokens_total")
        row = {
            "time": time.strftime("%H:%M:%S"),
            "running": pick(current, "vllm:num_requests_running"),
            "waiting": pick(current, "vllm:num_requests_waiting"),
            "kv_usage_pct": None if kv is None else 100 * kv,
            "preemptions": delta(current, previous, "vllm:num_preemptions_total"),
            "finished": delta(current, previous, "vllm:e2e_request_latency_seconds_count"),
            "e2e_s": hist_mean(current, previous, "vllm:e2e_request_latency_seconds"),
            "ttft_s": hist_mean(current, previous, "vllm:time_to_first_token_seconds"),
            "tpot_ms": None if tpot is None else 1000 * tpot,
            "prefill_tok_s": None if prompt_tokens is None else prompt_tokens / duration,
            "decode_tok_s": None if output_tokens is None else output_tokens / duration,
            "prefix_hit_pct": None if not queries else 100 * hits / queries,
        }
        values = [
            "" if row[field] is None else
            (row[field] if field == "time" else round(row[field], 2))
            for field in FIELDS
        ]
        writer.writerow(values)
        output_file.flush()
        print(" ".join(str(value) for value in values), flush=True)
        previous, previous_time = current, now
