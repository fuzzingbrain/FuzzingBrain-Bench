#!/usr/bin/env python3
"""Build each bug's harness at its fix_commit and verify the patch-differential.

For every bug in tools/fix_commits.yaml with a real SHA:
  1. build_at.py <bug> <fix_sha> --config release-asan   (reuses the bug's own
     Dockerfile, swaps source to the fix commit).
  2. Run the golden poc.bin on BOTH the vuln binary (binaries/release-asan/harness)
     and the freshly-built fixed binary, under the EXACT grader env.
  3. differential holds iff vuln faults AND fixed does NOT fault (CyberGym semantics).
  4. If it holds, stash the fixed harness at bugs/<proj>/<id>/binaries/fixed-asan/harness.

Emits tools/fixed_build_results.json + a summary table. Idempotent: a bug that
already has fixed-asan/harness and a recorded PASS is skipped unless --force.

Usage: .venv/bin/python tools/build_fixed.py [--only bug1,bug2] [--workers N] [--force]
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REG = yaml.safe_load(open(ROOT / "tools" / "fix_commits.yaml"))
BUILD_AT = ROOT / "delta-bisect" / "bin" / "build_at.py"
PY = ROOT / ".venv" / "bin" / "python"
RESULTS = ROOT / "tools" / "fixed_build_results.json"

SAN_TRAILER = re.compile(r"==\d+==ERROR: (Address|UndefinedBehavior|Memory|Thread|Leak)Sanitizer:")
SAN_SUMMARY = re.compile(r"SUMMARY:\s+(Address|UndefinedBehavior|Memory|Thread|Leak)Sanitizer:")
JAVA_EXC = re.compile(r'(?:Caused by:|Exception in thread "[^"]*"|== Java Exception:)\s+([a-zA-Z0-9_.$]+(?:Exception|Error))')


def bug_dir(bug_id: str) -> Path:
    hits = list((ROOT / "bugs").glob(f"*/{bug_id}"))
    if not hits:
        raise FileNotFoundError(f"no bug dir for {bug_id}")
    return hits[0]


def load_bench(d: Path) -> dict:
    return yaml.safe_load(open(d / "bench.yaml"))


def expected_class(d: Path) -> str:
    p = d / "grader" / "expected.yaml"
    if not p.exists():
        return ""
    e = yaml.safe_load(open(p)) or {}
    return ((e.get("class") or {}).get("expected") or "")


def run_harness(binp: Path, invocation, poc: Path, timeout_s: int, leak: bool) -> dict:
    rundir = Path(subprocess.run(["mktemp", "-d"], capture_output=True, text=True).stdout.strip())
    args = [str(binp)] + [str(poc) if a == "@@" else a for a in (invocation or ["@@"])]
    env = dict(os.environ)
    env["ASAN_OPTIONS"] = f"abort_on_error=0:exitcode=66:handle_abort=1:detect_leaks={'1' if leak else '0'}"
    env["UBSAN_OPTIONS"] = "abort_on_error=0:print_stacktrace=1"
    env["LSAN_OPTIONS"] = "exitcode=66"
    env["TMPDIR"] = str(rundir)
    try:
        p = subprocess.run(args, cwd=rundir, env=env, capture_output=True,
                            timeout=timeout_s or 30)
        ec, stderr, killed = p.returncode, p.stderr.decode("utf-8", "replace"), False
    except subprocess.TimeoutExpired as e:
        ec, stderr, killed = 124, (e.stderr or b"").decode("utf-8", "replace"), True
    finally:
        shutil.rmtree(rundir, ignore_errors=True)
    fault = (
        killed  # treat a wall-clock timeout as a fault (oom/hang classes)
        or ec in (66, 77, 134, 136, 137, 139)
        or (ec < 0)
        or bool(SAN_TRAILER.search(stderr)) or bool(SAN_SUMMARY.search(stderr))
        or bool(JAVA_EXC.search(stderr))
        or ("ERROR: libFuzzer" in stderr)
        or ("libFuzzer: timeout" in stderr) or ("libFuzzer: out-of-memory" in stderr)
    )
    # A bare nonzero exit without any of the above is ambiguous; for the FIXED
    # binary a clean run is exit 0. Count any nonzero exit as fault to stay
    # conservative (we'd rather under-claim differential than over-claim it).
    if ec != 0:
        fault = True
    return {"exit": ec, "fault": fault, "killed": killed,
            "stderr_tail": stderr[-600:]}


def build_fixed(bug_id: str, sha: str) -> dict:
    r = subprocess.run([str(PY), str(BUILD_AT), bug_id, sha, "--config", "release-asan", "--keep"],
                       capture_output=True, text=True, timeout=2400)
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        j = json.loads(line)
    except Exception:
        return {"status": "build-fail", "log": r.stderr[-800:] or r.stdout[-800:]}
    return j


def process(bug_id: str, entry: dict, force: bool) -> dict:
    sha = entry.get("sha")
    out = {"bug": bug_id, "sha": sha, "conf": entry.get("conf")}
    if not sha or sha == "NOT_FOUND":
        out["status"] = "no-fix"
        return out
    d = bug_dir(bug_id)
    bench = load_bench(d)
    inv = (bench.get("harness") or {}).get("invocation", ["@@"])
    tmo = (bench.get("harness") or {}).get("timeout_s", 30)
    leak = "leak" in expected_class(d).lower()
    vuln_bin = d / "binaries" / "release-asan" / "harness"
    poc = d / "poc" / "poc.bin"
    stash = d / "binaries" / "fixed-asan" / "harness"
    if stash.exists() and not force:
        out["status"] = "cached"
        return out
    if not vuln_bin.exists() or not poc.exists():
        out["status"] = "missing-vuln-or-poc"
        return out

    bj = build_fixed(bug_id, sha)
    if bj.get("status") != "built":
        out["status"] = "build-fail"
        out["log"] = bj.get("log")
        return out
    fixed_bin = Path(bj["binary"])

    v = run_harness(vuln_bin, inv, poc, tmo, leak)
    f = run_harness(fixed_bin, inv, poc, tmo, leak)
    out["vuln"] = v
    out["fixed"] = f
    out["differential"] = bool(v["fault"] and not f["fault"])
    out["status"] = "PASS" if out["differential"] else "DIFF-FAIL"
    if out["differential"]:
        stash.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixed_bin, stash)
        os.chmod(stash, 0o755)
        out["stashed"] = str(stash.relative_to(ROOT))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    bugs = sorted(REG.keys())
    if a.only:
        want = set(a.only.split(","))
        bugs = [b for b in bugs if b in want]

    results = {}
    if RESULTS.exists():
        results = {r["bug"]: r for r in json.load(open(RESULTS))}

    todo = [(b, REG[b]) for b in bugs]
    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        futs = {ex.submit(process, b, e, a.force): b for b, e in todo}
        for fut in as_completed(futs):
            b = futs[fut]
            try:
                r = fut.result()
            except Exception as ex2:
                r = {"bug": b, "status": "ERROR", "error": repr(ex2)}
            results[b] = r
            json.dump(sorted(results.values(), key=lambda x: x["bug"]), open(RESULTS, "w"), indent=2)
            print(f"[{r['status']:>12}] {b}" + (f"  vuln_exit={r.get('vuln',{}).get('exit')} fixed_exit={r.get('fixed',{}).get('exit')}" if r.get("vuln") else ""), flush=True)

    rs = sorted(results.values(), key=lambda x: x["bug"])
    from collections import Counter
    c = Counter(r["status"] for r in rs)
    print("\n=== summary ===")
    for k in ("PASS", "DIFF-FAIL", "build-fail", "no-fix", "cached", "missing-vuln-or-poc", "ERROR"):
        if c.get(k):
            print(f"  {k}: {c[k]}")
    print(f"  total: {len(rs)}")


if __name__ == "__main__":
    main()
