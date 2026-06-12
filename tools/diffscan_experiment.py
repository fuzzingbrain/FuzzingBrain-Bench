#!/usr/bin/env python3
"""Diff-scan experiment runner — names-only PR hint, with a noise ladder.

One invocation = one (bug, model, diff-level) episode. The agent gets NO bug
description, only the list of file names a PR "touched":

    diff-0 : just the crash-relevant file(s)
    diff-1 : crash file(s) + 1 random same-project distractor name
    diff-2 : crash file(s) + 2 distractors
    diff-3 : crash file(s) + 3 distractors

Everything else (harness, setup(), grader/oracle) is identical to full-scan. We
run a full-scan episode (so the system prompt withholds the description) and swap
the initial user message for the names-only PR-hint via monkeypatch, reusing the
exact episode loop / grading path.

Usage:
    PYTHONPATH=. python tools/diffscan_experiment.py \
        --bug libpng-zlib-inflate-uaf --model gpt-5.5 --diff-level 0 \
        --out-dir runs/diffscan/libpng-zlib-inflate-uaf/gpt-5.5/diff-0
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from fbbench.env import load_dotenv
from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.models import cost_usd
from fbbench.paths import REPO
from fbbench.runner.backends import make_backend
from fbbench.runner.mcp_client import stage_bug_view
import fbbench.runner.episode as episode_mod

import diffscan_lib as dl


def main() -> int:
    ap = argparse.ArgumentParser(description="Diff-scan (names-only) experiment runner")
    ap.add_argument("--bug", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--diff-level", type=int, required=True, choices=[0, 1, 2, 3])
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--max-turns", type=int, default=50)
    ap.add_argument("--require-preset", action="store_true",
                    help="off-target crash does not end the episode; keep iterating "
                         "until the preset capability set fires or max-turns is hit")
    args = ap.parse_args()

    load_dotenv(REPO)
    server_bin = str(REPO / "bin" / "mcp-server")
    if not Path(server_bin).is_file():
        print(f"error: mcp-server not found at {server_bin}", file=sys.stderr)
        return 2

    bug_dir = find_bug(args.bug, REPO)
    if bug_dir is None:
        print(f"error: bug {args.bug} not found", file=sys.stderr)
        return 2

    meta = dl.bug_meta(str(bug_dir))
    if not meta["crash_files"]:
        print(f"SKIP {args.bug}: no crash file in expected.yaml (site-less OOM/leak)",
              file=sys.stderr)
        return 3
    try:
        fl = dl.file_list(meta, args.diff_level)
    except NotImplementedError as e:
        print(f"SKIP {args.bug}: {e}", file=sys.stderr)
        return 3

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "diff_files.json").write_text(json.dumps({
        "bug_id": args.bug, "diff_level": args.diff_level, **fl}, indent=2))

    workspace = tempfile.mkdtemp(prefix=f"fbbench-{args.bug}-")
    bug_view = stage_bug_view(str(bug_dir), full_scan=True)

    episode_mod.build_initial_user_message = dl.diffscan_message_builder(
        fl["files"], args.diff_level)

    backend = make_backend(args.model)
    try:
        result = episode_mod.run_episode(
            backend=backend,
            bug_id=args.bug,
            bug_dir=bug_view,
            oracle_dir=str(bug_dir),
            workspace=workspace,
            server_bin=server_bin,
            max_turns=args.max_turns,
            episode_log=str(out_dir / "episode.jsonl"),
            capability_set=capability_set(bug_dir),
            pocs_dir=str(out_dir / "pocs"),
            force_full=False,
            full_scan=True,
            require_preset=args.require_preset,
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(bug_view, ignore_errors=True)

    tier_score = sum(1 for v in result.capabilities.values() if v == "fired")
    cost = cost_usd(result.model, result.input_tokens, result.output_tokens,
                    result.cache_read_tokens, result.cache_write_tokens)
    score = {
        "bug_id": result.bug_id, "model": result.model,
        "mode": "diff-scan", "diff_level": args.diff_level,
        "require_preset": args.require_preset,
        "changed_files": fl["files"], "crash_files": fl["crash"],
        "distractors": fl["distractors"],
        "capabilities": result.capabilities, "tier_score": tier_score,
        "terminated_reason": result.terminated_reason,
        "turns_used": result.turns_used, "duration_s": result.duration_s,
        "total_usd": cost["total_usd"],
    }
    (out_dir / "score.json").write_text(json.dumps(score, indent=2))
    (out_dir / "cost.json").write_text(json.dumps({"model": result.model, **cost},
                                                  indent=2))
    print(json.dumps(score, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
