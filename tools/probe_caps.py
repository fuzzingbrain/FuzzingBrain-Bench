#!/usr/bin/env python3
"""Probe the MAXIMAL gradeable capability set for each bug.

The grader only evaluates the capabilities listed in a bug's capability_set;
others are never checked. To find whether a bug *could* grade more than it
declares, this temporarily forces capability_set = [reach,crash,class,site],
runs `fb-bench grade`, records which capabilities actually fire, then restores
bench.yaml via git. It prints, per bug: declared set, fired set, and the diff
(UNDER = fires but not declared; OVER = declared but does not fire).

Run:  PYTHONPATH=. python tools/probe_caps.py [--all] [bug ...]
By default probes only bugs whose declared set is not the full four.
"""
from __future__ import annotations

import glob
import os
import re
import subprocess
import sys

import yaml

FULL = ["reach", "crash", "class", "site"]
LINE = re.compile(r"[●○]\s+T\d\s+(reach|crash|class|site)\s+(fired|not fired)")


CS_LINE = re.compile(r"^(\s*capability_set\s*:).*$", re.M)
ROUNDS = os.environ.get("PROBE_ROUNDS", "1")


def declared(bench_path):
    return yaml.safe_load(open(bench_path)).get("capability_set", [])


def probe(bug, bench_path):
    # Save the EXACT original text and restore it verbatim afterwards. Do a
    # line-level rewrite of just the capability_set line (never a yaml round-trip,
    # which would reformat the file and drop comments) and never `git checkout`
    # (which would clobber unrelated uncommitted edits in this same file).
    original = open(bench_path).read()
    forced = CS_LINE.sub(lambda m: f'{m.group(1)} [{", ".join(FULL)}]', original, count=1)
    try:
        open(bench_path, "w").write(forced)
        r = subprocess.run(["./fb-bench", "grade", bug, "-v", "--rounds", ROUNDS],
                           capture_output=True, text=True, timeout=600)
        fired = {m.group(1) for m in LINE.finditer(r.stdout + r.stderr)
                 if m.group(2) == "fired"}
    except subprocess.TimeoutExpired:
        fired = None
    finally:
        open(bench_path, "w").write(original)
    return fired


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    do_all = "--all" in sys.argv
    benches = {}
    for f in sorted(glob.glob("bugs/*/*/bench.yaml")):
        if "krb5" in f:
            continue
        bug = os.path.basename(os.path.dirname(f))
        if args and bug not in args:
            continue
        decl = declared(f)
        if not args and not do_all and sorted(decl) == sorted(FULL):
            continue
        benches[bug] = (f, decl)

    print(f"probing {len(benches)} bugs (forcing full capability_set)...\n")
    print(f"{'bug':42s} {'declared':22s} {'fired':22s} diff")
    for bug, (f, decl) in benches.items():
        fired = probe(bug, f)
        if fired is None:
            print(f"{bug:42s} {','.join(decl):22s} {'TIMEOUT':22s}")
            continue
        under = sorted(fired - set(decl))
        over = sorted(set(decl) - fired)
        diff = ""
        if under:
            diff += f"  UNDER(+{','.join(under)})"
        if over:
            diff += f"  OVER(-{','.join(over)})"
        ds = ",".join(c for c in FULL if c in decl)
        fs = ",".join(c for c in FULL if c in fired)
        print(f"{bug:42s} {ds:22s} {fs:22s}{diff}")


if __name__ == "__main__":
    main()
