#!/usr/bin/env python3
"""Build vuln_commit + an author-supplied strict-fix patch, verify the differential.

For each bug that has tools/fixes/<bug>.patch (and is not already covered by an
upstream fix), build the harness at vuln_commit with the patch applied, run the
golden PoC on vuln vs strict-fixed, and on a clean differential re-stash the fixed
bundle (self-contained) + record fix_commit = "vuln+strictfix:<patchsha>".

Usage: .venv/bin/python tools/build_strictfix.py [--only a,b]
"""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from pathlib import Path

import yaml
from build_fixed import bug_dir, load_bench, expected_class, run_harness  # reuse
from restash_fixed import restash

ROOT = Path(__file__).resolve().parent.parent
FIXES = ROOT / "tools" / "fixes"
MANIFEST = json.load(open(ROOT / "delta-bisect" / "manifest.json"))
BUILD_AT = ROOT / "delta-bisect" / "bin" / "build_at.py"
PY = ROOT / ".venv" / "bin" / "python"
STRICT_RESULTS = ROOT / "tools" / "strictfix_results.json"


def build(bug: str, vuln: str, patch: Path) -> dict:
    r = subprocess.run([str(PY), str(BUILD_AT), bug, vuln, "--config", "release-asan",
                        "--keep", "--patch", str(patch)],
                       capture_output=True, text=True, timeout=2400)
    line = (r.stdout.strip().splitlines() or [""])[-1]
    try:
        return json.loads(line)
    except Exception:
        return {"status": "build-fail", "log": (r.stderr or r.stdout)[-1000:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    patches = sorted(FIXES.glob("*.patch"))
    if a.only:
        want = set(a.only.split(","))
        patches = [p for p in patches if p.stem in want]

    results = {}
    if STRICT_RESULTS.exists():
        results = {r["bug"]: r for r in json.load(open(STRICT_RESULTS))}

    for p in patches:
        bug = p.stem
        out = {"bug": bug, "patch": p.name, "fix_commit": "vuln+strictfix:" +
               hashlib.sha1(p.read_bytes()).hexdigest()[:12]}
        if bug not in MANIFEST:
            out["status"] = "no-manifest"; results[bug] = out
            print(f"[ no-manifest] {bug}"); continue
        vuln = MANIFEST[bug]["vuln_commit"]
        d = bug_dir(bug); bench = load_bench(d)
        inv = (bench.get("harness") or {}).get("invocation", ["@@"])
        tmo = (bench.get("harness") or {}).get("timeout_s", 30)
        leak = "leak" in expected_class(d).lower()
        vuln_bin = d / "binaries" / "release-asan" / "harness"
        poc = d / "poc" / "poc.bin"

        bj = build(bug, vuln, p)
        if bj.get("status") != "built":
            out["status"] = "build-fail"; out["log"] = bj.get("log") or bj.get("msg")
            results[bug] = out; print(f"[  build-fail] {bug}: {str(out.get('log'))[:120]}"); continue
        fixed_bin = Path(bj["binary"])
        v = run_harness(vuln_bin, inv, poc, tmo, leak)
        f = run_harness(fixed_bin, inv, poc, tmo, leak)
        out["vuln"] = {"exit": v["exit"], "fault": v["fault"]}
        out["fixed"] = {"exit": f["exit"], "fault": f["fault"]}
        out["differential"] = bool(v["fault"] and not f["fault"])
        out["status"] = "PASS" if out["differential"] else "DIFF-FAIL"
        if out["differential"]:
            # restash reads RESULTS by sha; do the self-contained copy directly here
            note = restash(bug, vuln)  # builds path from out-<vuln[:12]>
            out["stash_note"] = note
        results[bug] = out
        json.dump(sorted(results.values(), key=lambda x: x["bug"]), open(STRICT_RESULTS, "w"), indent=2)
        print(f"[{out['status']:>11}] {bug}  vuln_exit={v['exit']} fixed_exit={f['exit']}"
              + (f"  {out.get('stash_note')}" if out["differential"] else ""))

    from collections import Counter
    print("\n=== strictfix summary ===", Counter(r["status"] for r in results.values()))


if __name__ == "__main__":
    main()
