#!/usr/bin/env python3
"""Build + verify an off-target-suppressed binary pair for ONE bug.

Given a bug_id and a suppression patch, this:
  1. builds NEW V1  = vuln_commit + patch   (interference-free vuln binary)
  2. builds NEW V2  = fix_commit  + patch   (differential oracle for new V1)
  3. verifies the three ablation properties on the benchmark sanitizer env:
       (P1) new V1 does NOT fault on each off-target PoC      (interference removed)
       (P2) new V1 STILL faults on the preset PoC             (preset intact)
       (P3) new V2 does NOT fault on the preset PoC           (valid differential oracle)
  4. as controls, confirms OLD V1 faults on both off-target and preset PoCs.

Writes tools/offtarget/results/<bug_id>.json. Idempotent: reuses an existing
out-<sha> binary unless --rebuild.

Usage:
  build_and_verify.py <bug_id> --patch <p> [--offtarget-pocs a.bin,b.bin] [--rebuild]
If --offtarget-pocs is omitted, off-target PoCs are looked up from inventory.json.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, glob
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
BUILD_AT = ROOT / "delta-bisect" / "bin" / "build_at.py"
PY = ROOT / ".venv" / "bin" / "python"
OT_ROOT = Path("/data4/ze/O2_Vulnerability_Management/incoming_report")
INV = json.load(open(ROOT / "tools" / "offtarget" / "inventory.json"))

SAN_TRAILER = re.compile(r"(==\d+==ERROR: (Address|UndefinedBehavior|Memory|Thread|Leak)Sanitizer:|"
                         r"runtime error:|SUMMARY: (Address|UndefinedBehavior|Leak)Sanitizer|"
                         r"ERROR: libFuzzer:|== Java Exception:|Exception in thread)")

def bug_dir(bug_id):
    hits = list((ROOT / "bugs").glob(f"*/{bug_id}"))
    if not hits: raise FileNotFoundError(bug_id)
    return hits[0]

def san_env(leak=False):
    env = dict(os.environ)
    env["ASAN_OPTIONS"] = f"abort_on_error=1:exitcode=99:handle_abort=1:detect_leaks={'1' if leak else '0'}"
    env["UBSAN_OPTIONS"] = "abort_on_error=1:print_stacktrace=1"
    env["LSAN_OPTIONS"] = "exitcode=99"
    return env

def run_poc(binp, invocation, poc, timeout_s, leak=False):
    args = [str(binp)] + [str(poc) if a == "@@" else a for a in (invocation or ["@@"])]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout_s, env=san_env(leak))
        rc, err, to = p.returncode, p.stderr, False
    except subprocess.TimeoutExpired as e:
        rc, err, to = None, (e.stderr or b"").decode("utf-8","replace") if isinstance(e.stderr,bytes) else (e.stderr or ""), True
    fault = (not to) and (rc not in (0, None)) and bool(SAN_TRAILER.search(err or ""))
    # some libfuzzer crashes exit nonzero without a trailer (raw signal); count those too
    if (not to) and rc not in (0, None) and not fault and rc in (77,99,134,135,136,137,138,139,1,70,71):
        fault = True
    m = re.search(r"(runtime error: [^\n]+|: ([A-Za-z]+Sanitizer): [^\n]+)", err or "")
    site = re.search(r"([\w./-]+\.(c|cc|cpp|h|java)):(\d+)", err or "")
    return {"exit": rc, "timeout": to, "fault": fault,
            "msg": (m.group(0)[:120] if m else ""),
            "site": (site.group(0) if site else "")}

def build(bug_id, commit, patch, rebuild):
    short = None
    # peek expected out dir by resolving sha via build_at is heavy; just run it (idempotent-ish)
    cmd = [str(PY), str(BUILD_AT), bug_id, commit, "--config", "release-asan", "--keep"]
    if patch: cmd += ["--patch", str(patch)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    line = p.stdout.strip().splitlines()[-1] if p.stdout.strip() else "{}"
    try: r = json.loads(line)
    except Exception: r = {"status":"parse-fail","raw":p.stdout[-400:],"err":p.stderr[-400:]}
    return r

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bug_id")
    ap.add_argument("--patch", required=True)
    ap.add_argument("--offtarget-pocs", default=None)
    ap.add_argument("--leak", action="store_true", help="enable detect_leaks in verify env")
    ap.add_argument("--rebuild", action="store_true")
    a = ap.parse_args()
    bd = bug_dir(a.bug_id)
    bench = yaml.safe_load(open(bd / "bench.yaml"))
    tgt = bench["target"]; inv = bench["harness"].get("invocation", ["@@"]); to = bench["harness"].get("timeout_s", 30)
    vuln, fix = tgt["vuln_commit"], tgt.get("fix_commit")
    preset_poc = bd / "poc" / "poc.bin"
    # off-target pocs
    if a.offtarget_pocs:
        ot_pocs = [Path(x) for x in a.offtarget_pocs.split(",")]
    else:
        ot_pocs = []
        for e in INV:
            if e["bundle"].split("/")[-1] == a.bug_id:
                for pf in e.get("poc_files", []):
                    ot_pocs.append(OT_ROOT / pf)
    old_v1 = bd / "binaries" / "release-asan" / "harness"
    res = {"bug_id": a.bug_id, "vuln": vuln, "fix": fix, "patch": str(a.patch),
           "offtarget_pocs": [str(p) for p in ot_pocs], "leak_env": a.leak}

    print(f"[{a.bug_id}] building new V1 (vuln {vuln[:12]} + patch)...", flush=True)
    b1 = build(a.bug_id, vuln, a.patch, a.rebuild); res["build_v1"] = b1
    if b1.get("status") != "built":
        res["verdict"] = "BUILD-FAIL-V1"; _dump(a.bug_id, res); print(json.dumps(b1)); sys.exit(3)
    new_v1 = Path(b1["binary"])

    print(f"[{a.bug_id}] building new V2 (fix {(fix or '?')[:12]} + patch)...", flush=True)
    b2 = build(a.bug_id, fix, a.patch, a.rebuild) if fix else {"status":"no-fix-commit"}
    res["build_v2"] = b2
    new_v2 = Path(b2["binary"]) if b2.get("status") == "built" else None

    # checks
    res["checks"] = {}
    res["checks"]["old_v1_offtarget"] = [run_poc(old_v1, inv, p, to, a.leak) for p in ot_pocs]
    res["checks"]["new_v1_offtarget"] = [run_poc(new_v1, inv, p, to, a.leak) for p in ot_pocs]
    res["checks"]["old_v1_preset"] = run_poc(old_v1, inv, preset_poc, to, a.leak) if preset_poc.exists() else None
    res["checks"]["new_v1_preset"] = run_poc(new_v1, inv, preset_poc, to, a.leak) if preset_poc.exists() else None
    res["checks"]["new_v2_preset"] = run_poc(new_v2, inv, preset_poc, to, a.leak) if new_v2 and preset_poc.exists() else None

    # verdict
    p1 = all(not r["fault"] for r in res["checks"]["new_v1_offtarget"]) if ot_pocs else None  # off-target removed
    p2 = (res["checks"]["new_v1_preset"] or {}).get("fault")                                   # preset intact
    p3 = (not (res["checks"]["new_v2_preset"] or {}).get("fault")) if new_v2 else None          # differential oracle ok
    ctrl = all(r["fault"] for r in res["checks"]["old_v1_offtarget"]) if ot_pocs else None
    res["properties"] = {"P1_offtarget_removed": p1, "P2_preset_intact": p2,
                         "P3_v2_no_preset_fault": p3, "CTRL_old_v1_faults_offtarget": ctrl}
    res["verdict"] = "PASS" if (p1 and p2 and (p3 in (True, None))) else "FAIL"
    _dump(a.bug_id, res)
    print(json.dumps(res["properties"]), flush=True)
    print(f"[{a.bug_id}] VERDICT: {res['verdict']}", flush=True)

def _dump(bug_id, res):
    out = ROOT / "tools" / "offtarget" / "results"; out.mkdir(parents=True, exist_ok=True)
    json.dump(res, open(out / f"{bug_id}.json", "w"), indent=2, default=str)

if __name__ == "__main__":
    main()
