#!/usr/bin/env python3
"""Re-stash fixed-asan bundles self-contained, for every PASS/cached bug.

The first stash copied only `harness`, which breaks bugs whose harness needs
sibling runtime files:
  * ELF + RUNPATH=$ORIGIN (e.g. systemd) -> needs the sibling .so next to it.
  * JVM launcher reading ${DIR}/../lib   -> needs the FIXED lib/ (the fix lives
    in the jars, not the script); we bundle it and repoint ../lib -> lib.

Self-contained layout produced at bugs/<proj>/<id>/binaries/fixed-asan/:
  harness            (the fixed harness; ELF stripped)
  *.so               (any sibling shared libs from the build out-dir; stripped)
  lib/               (JVM only: the fixed classpath; launcher repointed to ./lib)

Then re-grades each bug's golden PoC to confirm differential fires.
Usage: .venv/bin/python tools/restash_fixed.py [--only a,b] [--no-grade]
"""
from __future__ import annotations
import argparse, json, os, re, shutil, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = {r["bug"]: r for r in json.load(open(ROOT / "tools" / "fixed_build_results.json"))}
SRCCACHE = ROOT / "delta-bisect" / "src-cache"


def bug_dir(bug_id: str) -> Path:
    return next((ROOT / "bugs").glob(f"*/{bug_id}"))


def out_dir(bug_id: str, sha: str) -> Path:
    return SRCCACHE / bug_id / f"out-{sha[:12]}"


def strip_elf(p: Path):
    # strip --strip-all is a no-op (error, file untouched) on non-ELF (scripts).
    subprocess.run(["strip", "--strip-all", str(p)], capture_output=True)


def restash(bug_id: str, sha: str) -> str:
    od = out_dir(bug_id, sha)
    src_ra = od / "release-asan"
    if not (src_ra / "harness").exists():
        return f"NO-OUTDIR ({od.name})"
    dst = bug_dir(bug_id) / "binaries" / "fixed-asan"
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)

    # 1) harness + any sibling files in release-asan/ (e.g. *.so for $ORIGIN RUNPATH)
    for f in src_ra.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)
    os.chmod(dst / "harness", 0o755)

    notes = ["harness"]
    sos = [f.name for f in dst.iterdir() if f.suffix == ".so" or ".so." in f.name]
    if sos:
        notes.append(f"+{len(sos)}so")

    # 2) JVM: bundle the fixed lib/ and repoint the launcher's ../lib -> ./lib.
    src_lib = od / "lib"
    if src_lib.is_dir():
        shutil.copytree(src_lib, dst / "lib")
        h = dst / "harness"
        txt = h.read_text(errors="ignore")
        new = txt.replace('${DIR}/../lib', '${DIR}/lib').replace('$DIR/../lib', '$DIR/lib')
        if new != txt:
            h.write_text(new)
            notes.append("lib+repoint")
        else:
            notes.append("lib(no-repoint!)")

    # 3) strip ELF artifacts (harness + .so); scripts/jars are left untouched.
    for f in dst.rglob("*"):
        if f.is_file():
            strip_elf(f)

    return " ".join(notes)


def grade(bug_id: str) -> tuple[str, dict]:
    from fbbench.grading import grade_blob, capability_set
    d = bug_dir(bug_id)
    sc, _ = grade_blob(d, d / "poc" / "poc.bin", rounds=1)
    caps = sc["capabilities"]
    kb = capability_set(d)
    solved = all(caps.get(k) == "fired" for k in kb)
    return ("PASS" if (caps.get("differential") == "fired" and solved) else "FAIL"), caps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--no-grade", action="store_true")
    a = ap.parse_args()
    bugs = [b for b, r in RESULTS.items() if r.get("status") in ("PASS", "cached")]
    if a.only:
        want = set(a.only.split(","))
        bugs = [b for b in bugs if b in want]
    npass = 0
    for b in sorted(bugs):
        note = restash(b, RESULTS[b]["sha"])
        if a.no_grade:
            print(f"  [stashed] {b:<44} {note}")
            continue
        verdict, caps = grade(b)
        if verdict == "PASS":
            npass += 1
        print(f"  [{verdict}] {b:<44} {note:<22} differential={caps.get('differential')}")
    if not a.no_grade:
        print(f"\ndifferential PASS: {npass}/{len(bugs)}")


if __name__ == "__main__":
    main()
