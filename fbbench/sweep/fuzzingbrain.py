"""FuzzingBrain arm: drive the FuzzingBrain CRS "agent model" over the bench.

  python -m fbbench.sweep.fuzzingbrain one   <bug_id> [--model M] [--max-turns N]
  python -m fbbench.sweep.fuzzingbrain sweep [--bugs all|<csv>] [--model M]

This is the FuzzingBrain product competing as its own leaderboard arm, parallel
to the Codex (sweep/codex.py) and Claude-Code (sweep/claudecode.py) arms:

  - The bench MCP server IS the public canonical challenge image — we spawn
    `docker run -i --rm <image> mcp-server`, so the agent sees the SAME neutral
    discovery view, the SAME netns-isolated exec(), and grades via the SAME
    remote oracle as every other arm.
  - The agent itself is FuzzingBrain's native agent model
    (`fuzzingbrain.agent_model`, in the CRS repo): a Codex-style single-agent
    loop with a persistent plan, forced test-often pacing, post-test reflection,
    and a build-the-harness-and-fuzz-it methodology, powered by the CRS LLM brain.
  - run_input() returns only harness_output here (no reveal), exactly like the
    Codex arm; the authoritative capabilities come from re-grading the workspace
    blobs through the remote oracle.

The CRS lives in a SEPARATE repo/venv, so we launch it as a subprocess:
  $FUZZINGBRAIN_HOME  — the CRS v2 dir (contains the `fuzzingbrain` package).
  $FUZZINGBRAIN_PYTHON — a python with the CRS deps (default: its .agent_venv,
                         else python3).
`sweep` persists runs/<bug>/fuzzingbrain-<model>/seed-0/{score.json,...} and is
resumable.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from fbbench.env import load_dotenv
from fbbench.grading import capability_set, find_bug, list_bugs
from fbbench.models import cost_usd
from fbbench.paths import REPO
from fbbench.runner.mcp_client import _full_scan_alias
# Reuse the Codex arm's grading/blob helpers so scoring is identical across arms.
from fbbench.sweep.codex import (
    FLAGS, IMAGE_PREFIX, _best_caps, _candidate_blobs,
)

RUNS = REPO / "runs"
MAX_TURNS_DEFAULT = 100
DEFAULT_MODEL = "claude-haiku-4-5"

# Where the FuzzingBrain CRS lives (separate repo). Override with $FUZZINGBRAIN_HOME.
FB_HOME = os.environ.get(
    "FUZZINGBRAIN_HOME",
    os.path.expanduser("~/afc-crs-all-you-need-is-a-fuzzing-brain/v2"))


def _fb_python() -> str:
    """A python interpreter that can import the CRS `fuzzingbrain` package."""
    env = os.environ.get("FUZZINGBRAIN_PYTHON")
    if env:
        return env
    venv = os.path.join(FB_HOME, ".agent_venv", "bin", "python")
    return venv if os.path.isfile(venv) else "python3"


def model_label(model: str) -> str:
    """Leaderboard/result-dir label for this arm + model (e.g. fuzzingbrain-claude-haiku-4-5)."""
    return f"fuzzingbrain-{model}"


def _mcp_cmd(image: str, work: str) -> list[str]:
    """The `docker run … mcp-server` argv the agent drives — the canonical
    challenge image, workspace bind-mounted so candidate inputs survive the
    (--rm) container for post-hoc re-grading. Same shape as the Codex arm; no
    BENCH_GRADE_REVEAL, so run_input() returns only harness_output."""
    return ["docker", "run", "-i", "--rm",
            "--security-opt", "seccomp=unconfined",
            "-v", f"{work}:/workspace", image, "mcp-server"]


def _agent_cmd(model: str, max_turns: int, out_dir: str,
               mcp_cmd: list[str]) -> list[str]:
    """Launch the CRS agent model against the challenge MCP server."""
    return [_fb_python(), "-m", "fuzzingbrain.agent_model",
            "--model", model, "--max-turns", str(max_turns),
            "--out", out_dir, "--", *mcp_cmd]


def run_agent(bug: str, model: str, max_turns: int, timeout_s: int,
              out_dir: Path) -> dict:
    """Run the FuzzingBrain agent model on one challenge, then re-grade the
    workspace blobs via the remote oracle. Returns a score dict."""
    real = find_bug(bug)
    if not real:
        return {"error": f"bug not found: {bug}"}
    alias = _full_scan_alias(str(real))
    image = f"{IMAGE_PREFIX}{alias}"

    work = tempfile.mkdtemp(prefix=f"fb-{alias}-")
    os.chmod(work, 0o777)  # the container (root) writes candidate inputs here
    out_dir.mkdir(parents=True, exist_ok=True)

    # Make the model API key available to the CRS subprocess even when the caller
    # ran `python -m fbbench.sweep.fuzzingbrain` without exporting it (the bench
    # .env is auto-loaded for `fb-bench run`, but not for a bare module call).
    load_dotenv()
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", FB_HOME)
    env["PYTHONUNBUFFERED"] = "1"

    argv = _agent_cmd(model, max_turns, str(out_dir), _mcp_cmd(image, work))
    # Capture the agent's stderr so a subprocess failure (bad venv, missing key,
    # litellm error) is diagnosable instead of vanishing.
    err_path = out_dir / "agent_stderr.log"
    t0 = time.time()
    terminated = "completed"
    with open(err_path, "wb") as errf:
        try:
            subprocess.run(argv, env=env, cwd=FB_HOME, timeout=timeout_s,
                           stdout=subprocess.DEVNULL, stderr=errf)
        except subprocess.TimeoutExpired:
            terminated = "timeout"
    duration = time.time() - t0

    # Authoritative caps: re-grade every candidate blob through the remote oracle.
    blobs = _candidate_blobs(work)
    caps, best_blob, ts = _best_caps(alias, blobs)

    ar = {}
    ar_path = out_dir / "agent_result.json"
    if ar_path.is_file():
        try:
            ar = json.loads(ar_path.read_text())
        except (OSError, ValueError):
            ar = {}
    if ar.get("terminated_reason") and terminated == "completed":
        terminated = ar["terminated_reason"]

    kb = capability_set(real)
    solved = bool(kb) and all(caps.get(k) == "fired" for k in kb)
    if best_blob:
        shutil.copy(best_blob, out_dir / "best_blob")

    cost = cost_usd(model, ar.get("input_tokens", 0), ar.get("output_tokens", 0),
                    ar.get("cache_read_tokens", 0), ar.get("cache_write_tokens", 0))
    score = {
        "bug_id": bug, "model": model_label(model), "base_model": model, "seed": 0,
        "capabilities": {f: caps.get(f, "not_fired") for f in FLAGS},
        "tier_score": ts, "k_b": kb, "solved": solved,
        "terminated_reason": terminated,
        "turns_used": ar.get("turns_used"), "max_turns": max_turns,
        "duration_s": round(duration, 1),
        "tested": ar.get("tested"), "blobs_written": len(blobs),
        "total_usd": cost.get("total_usd"),
    }
    if ar.get("error"):
        score["agent_error"] = ar["error"]
    (out_dir / "score.json").write_text(json.dumps(score, indent=2))
    (out_dir / "cost.json").write_text(json.dumps({"model": model_label(model), **cost}, indent=2))

    # The agent already wrote transcript.jsonl in the report event format —
    # render the per-cell report exactly like the other arms.
    try:
        from fbbench.runner.report import write_report
        write_report(out_dir)
    except Exception as e:  # noqa: BLE001
        print(f"  report skipped: {e}")

    shutil.rmtree(work, ignore_errors=True)
    return score


def cmd_one(args) -> int:
    out_dir = RUNS / args.bug_id / model_label(args.model) / "one"
    print(f"  FuzzingBrain agent: {args.bug_id} / {model_label(args.model)} "
          f"(max_turns={args.max_turns})", flush=True)
    s = run_agent(args.bug_id, args.model, args.max_turns, args.timeout, out_dir)
    if "error" in s:
        sys.exit(s["error"])
    fired = [f for f in FLAGS if s["capabilities"][f] == "fired"]
    mark = "✓" if s["solved"] else "✗"
    print(f"\n  {mark} {s['tier_score']}/5  fired={fired}  "
          f"{s['terminated_reason']}  turns={s.get('turns_used')}/{args.max_turns}  "
          f"{s['duration_s']}s  blobs={s['blobs_written']}  ${s.get('total_usd') or 0:.4f}")
    print(f"  results -> {out_dir}")
    return 0


def run_sweep_cell(bug: str, model: str, max_turns: int, timeout_s: int) -> dict | None:
    cell = RUNS / bug / model_label(model) / "seed-0"
    if (cell / "score.json").is_file():
        return None  # already done
    return run_agent(bug, model, max_turns, timeout_s, cell)


def cmd_sweep(args) -> int:
    bugs = ([n for n, _ in list_bugs()] if args.bugs == "all"
            else [b.strip() for b in args.bugs.split(",") if b.strip()])
    label = model_label(args.model)
    done = sum(1 for b in bugs if (RUNS / b / label / "seed-0" / "score.json").is_file())
    print(f"  fuzzingbrain sweep ({label}): {len(bugs)} bugs "
          f"({done} done, {len(bugs)-done} to run)")
    t0 = time.time()
    solved_total = 0
    for i, bug in enumerate(bugs, 1):
        cell = RUNS / bug / label / "seed-0" / "score.json"
        if cell.is_file():
            s = json.loads(cell.read_text())
        else:
            print(f"  [{i}/{len(bugs)}] run {bug} ...", flush=True)
            s = run_sweep_cell(bug, args.model, args.max_turns, args.timeout)
            if not s or "error" in (s or {}):
                print(f"      skip/err: {(s or {}).get('error')}")
                continue
        mark = "✓" if s["solved"] else "✗"
        print(f"      {mark} {s['tier_score']}/5  {s['terminated_reason']}  "
              f"turns={s.get('turns_used')}/{s.get('max_turns','?')}  "
              f"{s['duration_s']}s  ${s.get('total_usd') or 0:.4f}")
        solved_total += int(s["solved"])
    print(f"\n  done in {time.time()-t0:.0f}s  solved {solved_total}/{len(bugs)}")
    try:
        from fbbench.report.summary import write_summary
        print(f"  summary -> {write_summary(RUNS)}")
    except Exception as e:  # noqa: BLE001
        print(f"  summary skipped: {e}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fbbench.sweep.fuzzingbrain",
                                 description="FuzzingBrain CRS agent-model arm")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp_one = sub.add_parser("one", help="run a single bug (keeps the cell dir)")
    sp_one.add_argument("bug_id")
    sp_one.add_argument("--model", default=DEFAULT_MODEL, help="base LLM model id")
    sp_one.add_argument("--max-turns", type=int, default=MAX_TURNS_DEFAULT)
    sp_one.add_argument("--timeout", type=int, default=2400,
                        help="per-bug wall-clock backstop seconds")
    sp_one.set_defaults(fn=cmd_one)

    sp_sweep = sub.add_parser("sweep", help="batch bugs, persist score.json (resumable)")
    sp_sweep.add_argument("--bugs", default="all", help="'all' or comma list")
    sp_sweep.add_argument("--model", default=DEFAULT_MODEL, help="base LLM model id")
    sp_sweep.add_argument("--max-turns", type=int, default=MAX_TURNS_DEFAULT)
    sp_sweep.add_argument("--timeout", type=int, default=2400,
                          help="per-bug wall-clock backstop seconds")
    sp_sweep.set_defaults(fn=cmd_sweep)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
