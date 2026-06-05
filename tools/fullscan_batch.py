#!/usr/bin/env python3
"""Re-run full-scan (no hint, harness only) under the CURRENT grader, so it can
be compared apples-to-apples against diff-scan. Preserves PoCs for future
re-grades. Concurrency + per-episode timeout + resume + summary.

Usage:
    PYTHONPATH=. python tools/fullscan_batch.py --model claude-haiku-4-5 --concurrency 6
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


def all_bugs():
    return sorted(os.path.basename(os.path.dirname(p))
                  for p in glob.glob(str(REPO / "bugs/*/*/bench.yaml")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--mode", choices=["full-scan", "normal"], default="full-scan")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--max-turns", type=int, default=50)
    ap.add_argument("--episode-timeout", type=int, default=1800)
    ap.add_argument("--out-root", default="runs/diffscan")
    ap.add_argument("--bugs", nargs="*")
    args = ap.parse_args()

    bugs = args.bugs or all_bugs()
    todo = []
    for b in bugs:
        out = Path(args.out_root) / b / args.model / args.mode
        if (out / "score.json").exists():
            continue
        todo.append((b, out))
    print(f"{args.mode} {args.model}: todo={len(todo)} (of {len(bugs)})")
    if not todo:
        print("nothing to run."); return 0

    env = {**os.environ, "PYTHONPATH": str(REPO)}
    running, done, i, t0 = {}, [], 0, time.time()
    while i < len(todo) or running:
        while i < len(todo) and len(running) < args.concurrency:
            bug, out = todo[i]; i += 1
            out.mkdir(parents=True, exist_ok=True)
            logf = open(out.parent / f"{args.mode}.batchlog", "w")
            cmd = [sys.executable, "-m", "fbbench.runner",
                   "--bug", bug, "--model", args.model,
                   "--preserve-pocs", "--out-dir", str(out),
                   "--max-turns", str(args.max_turns)]
            if args.mode == "full-scan":
                cmd.append("--full-scan")
            p = subprocess.Popen(cmd, env=env, stdout=logf,
                                 stderr=subprocess.STDOUT, start_new_session=True)
            running[p] = (bug, out, logf, time.time())
            print(f"  [{i}/{len(todo)}] start {bug}", flush=True)
        time.sleep(3)
        now = time.time()
        for p in list(running):
            bug, out, logf, st = running[p]
            if p.poll() is None:
                if now - st > args.episode_timeout:
                    try:
                        os.killpg(os.getpgid(p.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        p.kill()
                    logf.close(); running.pop(p)
                    done.append((bug, None, False, None))
                    print(f"  TIMEOUT {bug} killed after {now-st:.0f}s", flush=True)
                continue
            running.pop(p); logf.close()
            sc = out / "score.json"
            if sc.exists():
                s = json.loads(sc.read_text())
                fired = {k for k, v in s["capabilities"].items() if v == "fired"}
                kb = set(capability_set(find_bug(bug, REPO)) or
                         ["reach", "crash", "class", "site"])
                solved = bool(kb) and kb.issubset(fired)
                done.append((bug, s.get("tier_score"), solved, s.get("total_usd")))
                print(f"  done {bug:40s} solved={solved} ${s.get('total_usd')}", flush=True)
            else:
                done.append((bug, None, False, None))
                print(f"  FAIL {bug:40s} (rc={p.returncode})", flush=True)

    solved = sum(1 for d in done if d[2])
    cost = sum(d[3] for d in done if d[3])
    print("\n" + "=" * 60)
    print(f"FULL-SCAN {args.model}: {len(done)} run, solved={solved}, "
          f"cost=${cost:.2f}, wall={time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
