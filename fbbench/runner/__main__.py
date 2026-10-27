"""CLI entrypoint for the episode driver — `python -m fbbench.runner`.

One invocation = one (model, bug) episode written to --out-dir. Most users go
through `fb-bench run` (which wraps this, picks a model from .env, and creates
a unique output dir); the batch sweep also shells out to this entry per cell.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from fbbench.env import load_dotenv
from fbbench.grading.bench_yaml import find_bug, read_bench
from fbbench.images import DEFAULT_IMAGE_PREFIX, agent_image
from fbbench.models import CATALOG, PRICES, cost_usd, default_sweep
from fbbench.sweep.mcp_episode import AGENT_USD_CAP, AGENT_WALL_CAP_S
from fbbench.paths import REPO
from fbbench.runner.backends import make_backend
from fbbench.runner.episode import run_episode
from fbbench.runner.mcp_client import _full_scan_alias


def print_models() -> None:
    sweep = set(default_sweep())
    print(f"\n  {len(CATALOG)} supported models "
          "(any other provider id is still runnable via --model)\n")
    print(f"  {'model':26s} {'provider':10s} {'tier':9s} "
          f"{'in $/M':>7s} {'out $/M':>8s}  sweep")
    print(f"  {'-'*26} {'-'*10} {'-'*9} {'-'*7} {'-'*8}  -----")
    for model, provider, tier in CATALOG:
        rate = PRICES.get(model)
        ins = f"{rate[0]:.2f}" if rate else "?"
        outs = f"{rate[1]:.2f}" if rate else "?"
        mark = "✓" if model in sweep else ""
        print(f"  {model:26s} {provider:10s} {tier:9s} {ins:>7s} {outs:>8s}  {mark}")
    print("\n  default sweep (--model omitted in batch): " + ", ".join(default_sweep()))
    print()


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m fbbench.runner",
                                 description="FuzzingBrain Bench episode driver")
    ap.add_argument("--bug", help="challenge alias")
    ap.add_argument("--model", default="claude-opus-4-8", help="model id (claude*/gpt*/gemini*)")
    ap.add_argument("--max-turns", type=int, default=0,
                    help="turn budget per episode; 0 = no turn limit (default 0: "
                         "the episode is bounded by --timeout and --cost-cap only)")
    ap.add_argument("--cost-cap", type=float, default=AGENT_USD_CAP,
                    help="dollar cap per episode; 0 disables it (default: the agent "
                         f"arms' cap, ${AGENT_USD_CAP:g})")
    ap.add_argument("--timeout", type=int, default=AGENT_WALL_CAP_S,
                    help="wall-clock seconds per episode; the agent is told its "
                         "remaining time and the episode self-stops at the limit "
                         f"(default: the agent arms' cap, {AGENT_WALL_CAP_S}s)")
    ap.add_argument("--output", default="output", help="output root (legacy nesting <output>/<bug>/<model>/)")
    ap.add_argument("--out-dir", default=None,
                    help="literal output dir; takes precedence over --output")
    ap.add_argument("--preserve-pocs", action=argparse.BooleanOptionalAction, default=True,
                    help="save every graded candidate blob into pocs/{crashed,clean}/ "
                         "(default on; pass --no-preserve-pocs to disable)")
    ap.add_argument("--stop-on-crash", action=argparse.BooleanOptionalAction, default=False,
                    help="end the episode at the first crash "
                         "(default OFF, so the agent keeps hunting for more distinct "
                         "crashes until it stops or --max-turns)")
    ap.add_argument("--seed", type=int, default=None,
                    help="which sample of this (bug, model) cell this run is; recorded "
                         "with the run id so repeats can be told apart")
    ap.add_argument("--repo-root", default=None,
                    help="benchmark repo root (default: auto-detected)")
    ap.add_argument("--api-key", default=None, help="provider API key (or use the env var)")
    ap.add_argument("--image-prefix", default=DEFAULT_IMAGE_PREFIX,
                    help="unused: every arm runs the agent image "
                         "(override with FBBENCH_AGENT_IMAGE_PREFIX)")
    ap.add_argument("--list-models", action="store_true",
                    help="print the supported-model catalog and exit")
    args = ap.parse_args()

    if args.list_models:
        print_models()
        return 0
    if not args.bug:
        ap.error("--bug is required (or use --list-models)")

    repo_root = Path(args.repo_root) if args.repo_root else REPO
    load_dotenv(repo_root)

    bug_dir = find_bug(args.bug, repo_root)
    if bug_dir is None:
        print(f"error: bug {args.bug} not found under {repo_root}/bugs", file=sys.stderr)
        return 2

    # The agent runs in the agent image, as every other arm does: the published
    # challenge plus gdb/jdb and the call graph, grading in-container. A bug may pin its own
    # image via the optional top-level `image:` field in bench.yaml, tag included.
    bug_image = read_bench(Path(bug_dir) / "bench.yaml").get("image")
    image = bug_image or agent_image(_full_scan_alias(str(bug_dir)))
    out_dir = (Path(args.out_dir) if args.out_dir
               else Path(args.output) / args.bug / args.model)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.cost_cap and cost_usd(args.model, 0, 0).get("total_usd") is None:
        ap.error(f"--cost-cap needs a price for {args.model!r} in fbbench/models/pricing.py")
    backend = make_backend(args.model, api_key=args.api_key)
    pocs_dir = (out_dir / "pocs") if args.preserve_pocs else None
    # One id per episode, recorded in score.json so a result can be traced back
    # to the run that produced it. It decides no verdict and reaches nothing
    # outside this process — grading happens in the container, which needs no
    # identity to run a harness on a file. The model/arm/seed fields that used
    # to travel beside it were request headers for a grading service that no
    # longer exists; score.json already records all three.
    run_uid = uuid.uuid4().hex
    # Everything (challenge surface, workspace, grading) lives in the
    # image; the host stages nothing. bug_dir="/src" is the in-container view.
    ep_bug_dir = "/src"
    result = run_episode(
        backend=backend,
        bug_id=args.bug,
        bug_dir=ep_bug_dir,
        oracle_dir=str(bug_dir),
        workspace="",
        image=image,
        max_turns=args.max_turns,
        time_budget_s=args.timeout,
        cost_cap_usd=args.cost_cap or None,
        episode_log=str(out_dir / "episode.jsonl"),
        pocs_dir=str(pocs_dir) if pocs_dir else None,
        stop_on_crash=args.stop_on_crash,
    )

    score = {
        "bug_id": result.bug_id,
        "model": result.model,
        # Identity, not score: it names this episode so a result can be traced
        # back to the run that produced it.
        "run_uid": run_uid,
        # Every run knob that shaped this episode — surfaced verbatim in the
        # report so a result is fully reproducible from its own score.json.
        "config": {
            # Blind: the harness and the source at the vulnerable revision, and
            # nothing else. Recorded so a result carries the conditions it was
            # produced under.
            "mode": "full-scan",
            "max_turns": args.max_turns,
            "timeout_s": args.timeout,
            "cost_cap_usd": args.cost_cap,
            "stop_on_crash": bool(args.stop_on_crash),
            "preserve_pocs": bool(args.preserve_pocs),
            # Observed, not assumed: recorded only once something was actually
            # graded. "not-exercised" means the model never submitted a
            # candidate, so nothing graded and there is nothing to claim.
            "grading": result.grading or "not-exercised",
            "image": image,
            # The self-hosted server this episode held (None for an API model).
            "endpoint": (os.environ.get("OLLAMA_BASE_URL")
                         if getattr(backend, "local", False) else None),
        },
        # The metric: the number of DISTINCT crashes the agent found (unique
        # crash-type + top-frames signatures).
        "score": result.unique_crashes,
        "unique_crashes": result.unique_crashes,
        "crash_signatures": sorted(result.crash_signatures),
        # The same environment record the agent arms write.
        "debugger": result.debugger,
        "gdb_available": result.debugger == "gdb",
        "callgraph_available": result.callgraph_available,
        "gdb_source_map": result.gdb_source_map,
        "system_prompt_sent": result.system_prompt_sent,
        "terminated_reason": result.terminated_reason,
        "refusal_retries": result.refusal_retries,
        "malformed_retries": result.malformed_retries,
        "turns_used": result.turns_used,
        "duration_s": result.duration_s,
    }
    # Distinct crashes is the whole score. Deciding whether a crash is THE
    # defect a challenge was built around needs an answer key — the PoC, the
    # documented fault, a build at the fix commit — and none of that ships in a
    # challenge image, so nothing here can claim it.
    if result.error:
        score["error"] = result.error
    cost = {"model": result.model,
            **cost_usd(result.model, result.input_tokens, result.output_tokens,
                       result.cache_read_tokens, result.cache_write_tokens)}
    score["total_usd"] = cost["total_usd"]
    (out_dir / "score.json").write_text(json.dumps(score, indent=2))
    (out_dir / "cost.json").write_text(json.dumps(cost, indent=2))

    # Self-contained browsable report (best-effort; never fails the run).
    try:
        from fbbench.runner.report import write_report
        write_report(out_dir)
    except Exception:  # noqa: BLE001
        pass

    print(json.dumps(score, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
