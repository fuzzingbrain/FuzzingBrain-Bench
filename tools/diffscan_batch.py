#!/usr/bin/env python3
"""Batch runner for the diff-scan experiment over all bugs.

Runs one (model, diff-level) cell across every bug, with a concurrency cap,
resume (skips bugs that already have a score.json), and a final summary table.
Bugs with no crash file (site-less OOM/leak) are skipped automatically; for
diff-level > 0, non-GitHub repos (no tree fetcher yet) are skipped too.

Usage:
    PYTHONPATH=.:tools python tools/diffscan_batch.py \
        --model claude-haiku-4-5 --diff-level 0 --concurrency 6
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.paths import REPO

import diffscan_lib as dl


def all_bugs() -> list[str]:
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(str(REPO / "bugs/*/*/bench.yaml")))


def runnable(bug: str, level: int) -> tuple[bool, str]:
    bug_dir = next(iter(glob.glob(str(REPO / f"bugs/*/{bug}"))), None)
    if not bug_dir:
        return False, "no bug dir"
    meta = dl.bug_meta(bug_dir)
    if not meta["crash_files"]:
        return False, "no crash file (OOM/leak)"
    if level > 0:
        # need a file tree for distractors — ok for GitHub, or any repo whose
        # tree we've pre-cached (binutils/libaom fetched via git clone).
        try:
            dl.fetch_tree(meta)
        except Exception:
            return False, "no fetchable file tree"
    return True, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--diff-level", type=int, required=True, choices=[0, 1, 2, 3])
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--max-turns", type=int, default=50)
    ap.add_argument("--episode-timeout", type=int, default=1500,
                    help="kill an episode after this many seconds (anti-hang)")
    ap.add_argument("--out-root", default="runs/diffscan")
    ap.add_argument("--require-preset", action="store_true",
                    help="force-preset mode: off-target crash does not end the episode")
    ap.add_argument("--bugs", nargs="*", help="subset of bug ids (default: all)")
    args = ap.parse_args()
    cell = f"diff-{args.diff_level}" + ("-preset" if args.require_preset else "")

    bugs = args.bugs or all_bugs()
    todo, skipped = [], []
    for b in bugs:
        ok, why = runnable(b, args.diff_level)
        if not ok:
            skipped.append((b, why)); continue
        out = Path(args.out_root) / b / args.model / cell
        if (out / "score.json").exists():
            skipped.append((b, "already done")); continue
        todo.append((b, out))

    print(f"model={args.model} {cell}  "
          f"todo={len(todo)} skipped={len(skipped)} (of {len(bugs)})")
    for b, why in skipped:
        print(f"  skip {b:40s} {why}")
    if not todo:
        print("nothing to run.")
        return 0

    env = {**os.environ, "PYTHONPATH": f"{REPO}:{REPO}/tools"}
    running: dict = {}   # proc -> (bug, out, logf, start)
    done = []
    i = 0
    t0 = time.time()
    while i < len(todo) or running:
        while i < len(todo) and len(running) < args.concurrency:
            bug, out = todo[i]; i += 1
            out.mkdir(parents=True, exist_ok=True)
            logf = open(out.parent / f"{cell}.batchlog", "w")
            cmd = [sys.executable, str(REPO / "tools/diffscan_experiment.py"),
                   "--bug", bug, "--model", args.model,
                   "--diff-level", str(args.diff_level),
                   "--out-dir", str(out), "--max-turns", str(args.max_turns)]
            if args.require_preset:
                cmd.append("--require-preset")
            p = subprocess.Popen(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT,
                                 start_new_session=True)
            running[p] = (bug, out, logf, time.time())
            print(f"  [{i}/{len(todo)}] start {bug}")
        time.sleep(3)
        now = time.time()
        for p in list(running):
            bug, out, logf, st = running[p]
            if p.poll() is None:
                # Kill hung episodes (e.g. a harness that wedges on some input)
                # so one stuck run can't pin a concurrency slot for hours.
                if now - st > args.episode_timeout:
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        p.kill()
                    logf.close()
                    running.pop(p)
                    done.append((bug, None, [], None, now - st, False))
                    print(f"  TIMEOUT {bug:40s} killed after {now-st:.0f}s")
                continue
            running.pop(p)
            logf.close()
            sc = out / "score.json"
            if sc.exists():
                s = json.loads(sc.read_text())
                fired = [k for k, v in s["capabilities"].items() if v == "fired"]
                # SOLVED = the bug's own capability_set K_b is satisfied, NOT
                # tier_score>=4 (K_b varies per bug: some are 2- or 3-capability).
                kb = set(capability_set(find_bug(bug, REPO)))
                solved = bool(kb) and kb.issubset(set(fired))
                done.append((bug, s["tier_score"], fired, s.get("total_usd"),
                             s.get("duration_s", 0), solved))
                print(f"  done {bug:40s} score={s['tier_score']} solved={solved} "
                      f"fired={fired} ${s.get('total_usd')}")
            else:
                done.append((bug, None, [], None, 0, False))
                print(f"  FAIL {bug:40s} (rc={p.returncode}, no score.json)")

    # summary
    print("\n" + "=" * 70)
    print(f"SUMMARY  model={args.model} {cell}  "
          f"({len(done)} run, {time.time()-t0:.0f}s wall)")
    solved = sum(1 for r in done if r[5])
    reached = sum(1 for r in done if "reach" in r[2])
    crashed = sum(1 for r in done if "crash" in r[2])
    cost = sum(r[3] for r in done if r[3])
    print(f"  reach={reached}  crash={crashed}  solved(K_b)={solved}  "
          f"total_cost=${cost:.2f}")
    print("=" * 70)
    for bug, ts, fired, c, dur, solved in sorted(done, key=lambda x: -(x[1] or -1)):
        cs = f"${c:.3f}" if c is not None else "  -  "
        print(f"  {bug:42s} score={ts if ts is not None else '?'} {'SOLVED' if solved else '      '} "
              f"{','.join(fired):20s} {cs}  {dur/60:.1f}m")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
