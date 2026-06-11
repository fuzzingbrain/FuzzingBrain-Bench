#!/usr/bin/env python3
"""Audit every file path cited in each bug's description.txt.

Two stages, per the request:
  1) EXISTS — does the cited file resolve to a real file (in the vuln-commit
     source tree, the bug's harness/, or the bug bundle)?
  2) CORRECT — for a `path:line` citation that resolves, is the line number
     within the file (i.e. not past EOF)?  The cited line's text is printed so
     a reviewer can eyeball whether it is the right line.

Output: per-bug problems (NOT-FOUND / LINE-OOB / AMBIGUOUS) plus a summary.
Run:  PYTHONPATH=.:tools python tools/audit_paths.py [--bug NAME] [--verbose]
"""
from __future__ import annotations

import argparse
import glob
import os
import re

import yaml

from fbbench.runner.mcp_client import _ensure_source_cache

# token like  a/b/c.cpp:123  or  foo.c  (path chars + a source extension + opt :line)
# NOTE: order extensions longest-first so ".cpp"/".cc" win over ".c".
EXTS = "cpp|cxx|cc|hpp|hh|inc|java|rs|go|py|in|h|c"
# (?![A-Za-z]) so a method call like `pattern.charAt` is NOT read as `pattern.c`;
# the extension must end the token (followed by ':', whitespace, ')', etc.).
PAT = re.compile(r"([A-Za-z0-9_./<>+-]+\.(?:" + EXTS + r"))(?![A-Za-z])(?::(\d+))?")
# bare basenames that are stdlib/system or build noise — not bug-source paths
IGNORE_BASENAMES = {
    "demangle.h", "stdio.h", "stdlib.h", "string.h", "stdint.h", "stddef.h",
    "build.rs", "build.sh",
}


def _tree_index(cache: str):
    """full-path set + basename->[fullpaths] for a source cache dir."""
    full, by_base = set(), {}
    if not cache:
        return full, by_base
    for dp, _, files in os.walk(cache):
        for fn in files:
            rel = os.path.relpath(os.path.join(dp, fn), cache).replace(os.sep, "/")
            full.add(rel)
            by_base.setdefault(fn, []).append(rel)
    return full, by_base


def _line_count(path: str) -> int:
    try:
        with open(path, "rb") as fp:
            return sum(1 for _ in fp)
    except OSError:
        return -1


def audit_bug(bug_dir: str, verbose: bool):
    bug = os.path.basename(bug_dir.rstrip("/"))
    desc = os.path.join(bug_dir, "description.txt")
    if not os.path.isfile(desc):
        return None
    bench = yaml.safe_load(open(os.path.join(bug_dir, "bench.yaml"))) or {}
    tgt = bench.get("target", {}) or {}
    cache = _ensure_source_cache(tgt.get("repo", ""), tgt.get("vuln_commit", ""))
    full, by_base = _tree_index(cache)
    # local bundle files the description may legitimately cite
    bundle = set()
    for sub in ("harness", "poc"):
        p = os.path.join(bug_dir, sub)
        if os.path.isdir(p):
            bundle |= set(os.listdir(p))

    problems = []
    cited = {}
    text = open(desc).read()
    for m in PAT.finditer(text):
        path, line = m.group(1), m.group(2)
        # skip URL fragments (https://host.com/... gets ".com" truncated to ".c")
        ctx = text[max(0, m.start() - 10):m.start()]
        if "//" in path or "://" in ctx or "http" in ctx or "google" in path or "github" in path:
            continue
        cited.setdefault(path, set()).add(int(line) if line else None)

    # basenames pinned by a fully-qualified citation elsewhere in the same
    # description -> a bare shorthand later is not "ambiguous"
    qualified = set()
    for path in cited:
        b = os.path.basename(path)
        if path in full or (b in by_base and len(by_base[b]) == 1):
            qualified.add(b)

    for path, lines in sorted(cited.items()):
        base = os.path.basename(path)
        if base in IGNORE_BASENAMES:
            continue
        # resolve -> list of candidate full repo-relative paths
        cands = []
        if path in full:
            cands = [path]
        elif base in by_base:
            cands = list(by_base[base])
        elif base in bundle:
            if verbose:
                problems.append(f"ok (bundle) {path}")
            continue
        else:
            problems.append(f"NOT-FOUND  {path}")
            continue
        if len(cands) > 1 and path not in full and base not in qualified:
            problems.append(f"AMBIGUOUS  {path}  -> {cands[:4]} (description should use a fuller path)")
        # line-in-range: a cited line is OK if it fits in ANY candidate file
        for ln in sorted(x for x in lines if x):
            counts = {c: _line_count(os.path.join(cache, c)) for c in cands}
            if all(n >= 0 and ln > n for n in counts.values()):
                worst = max(counts.values())
                problems.append(f"LINE-OOB   {path}:{ln}  (largest candidate has {worst} lines)")
            elif verbose:
                c0 = next(c for c, n in counts.items() if n < 0 or ln <= n)
                txt = open(os.path.join(cache, c0)).read().splitlines()
                problems.append(f"ok {c0}:{ln}  | {txt[ln-1].strip()[:70]}")
    return bug, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bug")
    ap.add_argument("--verbose", action="store_true", help="print every resolved line's text")
    args = ap.parse_args()
    bug_dirs = []
    for f in sorted(glob.glob("bugs/*/*/bench.yaml")):
        if "krb5" in f:
            continue
        d = os.path.dirname(f)
        if args.bug and os.path.basename(d) != args.bug:
            continue
        bug_dirs.append(d)

    total_problems = 0
    clean = 0
    for d in bug_dirs:
        r = audit_bug(d, args.verbose)
        if r is None:
            continue
        bug, problems = r
        real = [p for p in problems if not p.startswith("ok ")]
        if real or args.verbose:
            print(f"\n=== {bug} ===")
            for p in problems:
                print(f"  {p}")
        if real:
            total_problems += len(real)
        else:
            clean += 1
    print(f"\n──────── summary: {clean} clean, {total_problems} problems across {len(bug_dirs)} bugs ────────")


if __name__ == "__main__":
    main()
