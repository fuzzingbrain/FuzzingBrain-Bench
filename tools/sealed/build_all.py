#!/usr/bin/env python3
"""Batch-produce sealed challenges for the whole corpus.

For every bug:
  1. assemble the private ORACLE bundle into <oracle-root>/<bug> (symlink to the
     real bug dir — has binaries+expected+poc+fix_commit; consumed by the grade
     server, never shipped).
  2. build the public CHALLENGE image (answer-free, leak-audited) via
     build_challenge.py.

Emits a coverage + leak-audit report. Resumable: an existing challenge image is
skipped unless --force. Image build is the slow part; run in the background.

Usage:
  build_all.py [--only a,b] [--grade-url URL] [--oracle-root DIR] [--no-build] [--force]
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fbbench.runner.mcp_client import _full_scan_alias  # noqa: E402

def all_bugs():
    out = subprocess.run(["git", "ls-files", "bugs/*/*/bench.yaml"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return sorted(line.split("/")[2] for line in out.splitlines() if line.strip())

def bug_dir(bug):
    hits = list((ROOT / "bugs").glob(f"*/{bug}"))
    return hits[0] if hits else None

def image_exists(tag):
    return subprocess.run(["docker", "image", "inspect", tag],
                          capture_output=True).returncode == 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--grade-url", default="http://172.17.0.1:8077")
    ap.add_argument("--oracle-root", default=str(ROOT / "tools" / "sealed" / "oracle-root"))
    ap.add_argument("--tag-prefix", default="fbbench-challenge")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    bugs = a.only.split(",") if a.only else all_bugs()
    oracle_root = Path(a.oracle_root); oracle_root.mkdir(parents=True, exist_ok=True)
    report = {"built": [], "skipped": [], "leak_fail": [], "build_fail": [], "no_dir": []}

    for bug in bugs:
        bd = bug_dir(bug)
        if bd is None:
            report["no_dir"].append(bug); print(f"NO-DIR  {bug}", flush=True); continue
        alias = _full_scan_alias(str(bd.resolve()))
        # 1. oracle bundle (private) — symlink the real bug dir, keyed by the public
        #    ALIAS so the grade server resolves oracle-root/<alias> from BENCH_BUG_ID.
        link = oracle_root / alias
        if link.exists() or link.is_symlink():
            link.unlink()
        os.symlink(bd.resolve(), link)
        # 2. challenge image (public) — tagged by alias inside build_challenge.py
        tag = f"{a.tag_prefix}/{alias}:latest"
        if not a.force and not a.no_build and image_exists(tag):
            report["skipped"].append(bug); print(f"SKIP    {bug} (image exists)", flush=True); continue
        cmd = [sys.executable, str(ROOT / "tools" / "sealed" / "build_challenge.py"),
               bug, "--grade-url", a.grade_url, "--tag-prefix", a.tag_prefix]
        if a.no_build:
            cmd.append("--no-build")
        r = subprocess.run(cmd, capture_output=True, text=True)
        tail = (r.stdout + r.stderr).strip().splitlines()
        last = tail[-1] if tail else ""
        if r.returncode == 0:
            report["built"].append(bug); print(f"BUILT   {bug}", flush=True)
        elif r.returncode == 3:
            report["leak_fail"].append(bug); print(f"LEAK!   {bug}: {last}", flush=True)
        else:
            report["build_fail"].append(bug); print(f"FAIL    {bug}: {last}", flush=True)

    out = ROOT / "tools" / "sealed" / "build_report.json"
    json.dump(report, open(out, "w"), indent=2)
    print(f"\n=== sealed build: built={len(report['built'])} skipped={len(report['skipped'])} "
          f"leak_fail={len(report['leak_fail'])} build_fail={len(report['build_fail'])} "
          f"no_dir={len(report['no_dir'])} / {len(bugs)} ===")
    if report["leak_fail"]: print("LEAK FAILURES:", report["leak_fail"])
    if report["build_fail"]: print("BUILD FAILURES:", report["build_fail"])
    print(f"oracle-root: {oracle_root}  ({len(list(oracle_root.iterdir()))} bundles)")

if __name__ == "__main__":
    main()
