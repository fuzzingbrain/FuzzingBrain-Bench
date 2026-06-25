#!/usr/bin/env python3
"""Stage the Arm-B (interference-free) oracle tree for the off-target ablation.

For each bug that has a PASSing new-V1 build (tools/offtarget/results/<bug>.json),
create bugs-armB/<proj>/<bug>/ whose source/grader/poc are SYMLINKS to the real
bundle (identical agent-facing view) but whose binaries/ is a real copy with
release-asan/harness REPLACED by the new V1 (off-target suppressed). fixed-asan
(crash2 oracle) is kept from the real bundle (old V2) unless a new V2 exists.

Result: running the runner with repo_root=bugs-armB swaps ONLY the oracle binary
the agent probes via grade() — a clean independent variable, invisible to the agent.

Usage: stage_armB.py [--only bug1,bug2] [--list]
"""
from __future__ import annotations
import argparse, json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tools" / "offtarget" / "results"
ARMB = ROOT / "bugs-armB"

def bug_dir(bug_id):
    hits = list((ROOT / "bugs").glob(f"*/{bug_id}"))
    return hits[0] if hits else None

def new_v1_path(bug_id, vuln_sha):
    short = vuln_sha[:12]
    # build_at resolves tags->sha; the result json records the exact binary path
    r = json.load(open(RESULTS / f"{bug_id}.json"))
    b = r.get("build_v1", {})
    return Path(b["binary"]) if b.get("status") == "built" else None

def _swap_lib(binary_path, dst_lib):
    """If the build out-dir (binary's grandparent) has a lib/ (JVM bugs), copy it
    over dst_lib so the staged launcher loads the PATCHED jar. Returns True if a
    lib was swapped, False for non-JVM bugs (no lib/ in out-dir)."""
    out_lib = Path(binary_path).parent.parent / "lib"   # out-<sha>/lib
    if not out_lib.is_dir():
        return False
    if dst_lib.exists() or dst_lib.is_symlink():
        if dst_lib.is_symlink(): dst_lib.unlink()
        else: shutil.rmtree(dst_lib)
    dst_lib.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(out_lib, dst_lib, symlinks=False)
    return True


def stage_one(bug_id):
    rp = RESULTS / f"{bug_id}.json"
    if not rp.exists(): return (bug_id, "no-result")
    r = json.load(open(rp))
    if r.get("verdict") != "PASS": return (bug_id, f"verdict={r.get('verdict')}")
    bd = bug_dir(bug_id)
    if bd is None: return (bug_id, "no-bundle")
    nv1 = Path(r["build_v1"]["binary"])
    if not nv1.exists(): return (bug_id, "new-v1-missing")
    proj = bd.parent.name
    dst = ARMB / proj / bug_id
    if dst.exists(): shutil.rmtree(dst)
    dst.mkdir(parents=True)
    # symlink every top-level entry except binaries/
    for entry in os.listdir(bd):
        if entry == "binaries": continue
        os.symlink((bd / entry).resolve(), dst / entry)
    # real copy of binaries/, then swap release-asan/harness with new V1
    shutil.copytree(bd / "binaries", dst / "binaries", symlinks=False,
                    ignore=shutil.ignore_patterns())  # follow into real files
    ra = dst / "binaries" / "release-asan" / "harness"
    ra.parent.mkdir(parents=True, exist_ok=True)
    if ra.exists() or ra.is_symlink(): ra.unlink()
    shutil.copy2(nv1, ra); os.chmod(ra, 0o755)
    # JVM bugs: the patched code lives in the build out-dir's lib/ (loaded by the
    # release-asan launcher via ../lib = binaries/lib), NOT in the harness launcher
    # itself. Swap that lib too, else Arm B silently runs the UNPATCHED jar.
    jvm_v1 = _swap_lib(nv1, dst / "binaries" / "lib")
    # crash2 oracle: KEEP the original fixed-asan (old V2), do NOT swap in a
    # "new V2" (fix_commit + off-target patch). Off-target suppression is a
    # V1-ONLY concern; crash2 only needs the fixed binary to not-fault on the
    # input, which the original validated fixed binary already does. Building a
    # new V2 risks the off-target patch (authored against the VULN commit's line
    # numbers) landing wrong on the FIX tree and breaking the preset fix — which
    # is exactly what corrupted pdfbox's crash2. So we leave fixed-asan untouched.
    v2 = "old-V2(kept)" + (" +patched-lib" if jvm_v1 else "")
    return (bug_id, f"STAGED ({v2})")

def relink_one(bug_id):
    """Recreate the absolute symlinks (source/grader/etc.) for a bug whose
    binaries/ subtree is already present (e.g. after a fresh LFS checkout). Does
    NOT touch binaries/. Makes a git-committed bugs-armB/<bug>/binaries usable."""
    bd = bug_dir(bug_id)
    if bd is None: return (bug_id, "no-bundle")
    proj = bd.parent.name
    dst = ARMB / proj / bug_id
    if not (dst / "binaries").is_dir(): return (bug_id, "no-binaries (LFS not pulled?)")
    for entry in os.listdir(bd):
        if entry == "binaries": continue
        link = dst / entry
        if link.exists() or link.is_symlink():
            if link.is_symlink(): link.unlink()
            else: continue
        os.symlink((bd / entry).resolve(), link)
    return (bug_id, "RELINKED")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--relink", action="store_true",
                    help="recreate source symlinks for an existing binaries/ (post-clone); no rebuild")
    a = ap.parse_args()
    pass_bugs = []
    for rp in sorted(RESULTS.glob("*.json")):
        r = json.load(open(rp))
        if r.get("verdict") == "PASS": pass_bugs.append(rp.stem)
    if a.list:
        print("PASS bugs ready to stage:", pass_bugs); return
    todo = a.only.split(",") if a.only else pass_bugs
    fn = relink_one if a.relink else stage_one
    for b in todo:
        print("  %-44s %s" % fn(b))
    print(f"\nArm-B tree at {ARMB} ({len(todo)} bugs)")

if __name__ == "__main__":
    main()
