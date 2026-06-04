#!/usr/bin/env python3
"""Re-grade saved candidate blobs through the current mcp-server grader.

No model calls — just replays each preserved PoC blob through grade() and reports
the capabilities the (current) grader computes. Use after a grader fix to refresh
results without re-running episodes.

Usage:
    PYTHONPATH=. python tools/regrade.py <bug_id> <blob.bin> [blob2.bin ...]
    PYTHONPATH=. python tools/regrade.py <bug_id> --pocs-dir <dir>   # all blobs in dir
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sys
import tempfile

from fbbench.grading.bench_yaml import capability_set, find_bug
from fbbench.paths import REPO
from fbbench.runner.mcp_client import MCPClient, stage_bug_view


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bug")
    ap.add_argument("blobs", nargs="*")
    ap.add_argument("--pocs-dir")
    ap.add_argument("--server-bin", default=str(REPO / "bin" / "mcp-server"))
    args = ap.parse_args()

    bug_dir = find_bug(args.bug, REPO)
    if bug_dir is None:
        print(f"bug {args.bug} not found", file=sys.stderr); return 2
    kb = set(capability_set(bug_dir))

    blobs = list(args.blobs)
    if args.pocs_dir:
        blobs += sorted(glob.glob(os.path.join(args.pocs_dir, "**", "*.bin"), recursive=True))
    if not blobs:
        print("no blobs given", file=sys.stderr); return 2

    workspace = tempfile.mkdtemp(prefix=f"regrade-{args.bug}-")
    bug_view = stage_bug_view(str(bug_dir), full_scan=False)
    mcp = MCPClient(args.server_bin, bug_dir=bug_view, workspace=workspace,
                    oracle_dir=str(bug_dir))
    mcp.initialize(); mcp.call("setup", {})

    best = {"reach": "n/a", "crash": "n/a", "class": "n/a", "site": "n/a"}
    try:
        for b in blobs:
            dst = os.path.join(workspace, os.path.basename(b))
            shutil.copy2(b, dst)
            out = mcp.call("grade", {"path": dst})
            caps = out.get("capabilities", {})
            fired = sorted(k for k, v in caps.items() if v == "fired")
            for k, v in caps.items():
                if v == "fired":
                    best[k] = "fired"
            print(f"  {os.path.basename(b):28s} fired={fired}")
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
        shutil.rmtree(bug_view, ignore_errors=True)

    best_fired = sorted(k for k, v in best.items() if v == "fired")
    tier = len(best_fired)
    solved = bool(kb) and kb.issubset(set(best_fired))
    print(f"\n{args.bug}: best across {len(blobs)} blobs -> fired={best_fired} "
          f"tier={tier} K_b={sorted(kb)} SOLVED={solved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
