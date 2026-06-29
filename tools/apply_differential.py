#!/usr/bin/env python3
"""Stamp differential + fix_commit into bench.yaml for every bug whose patch-differential
build PASSed (tools/fixed_build_results.json, status == PASS).

- capability_set: insert `differential` immediately after `crash` (idempotent).
- target.fix_commit: record the verified fix SHA next to vuln_commit (idempotent).

Edits are textual to preserve the file's formatting/comments. Dry-run by default;
pass --write to apply.

Usage: .venv/bin/python tools/apply_differential.py [--write]
"""
from __future__ import annotations
import argparse, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = json.load(open(ROOT / "tools" / "fixed_build_results.json"))
_SF = ROOT / "tools" / "strictfix_results.json"
STRICTFIX = {r["bug"]: r for r in json.load(open(_SF))} if _SF.exists() else {}


def bug_dir(bug_id: str) -> Path:
    return next((ROOT / "bugs").glob(f"*/{bug_id}"))


def edit_bench(path: Path, sha: str, patch: str | None = None) -> tuple[bool, str]:
    text = path.read_text()
    orig = text
    notes = []

    # 1) capability_set: [..] — insert differential after crash.
    m = re.search(r"^capability_set:\s*\[([^\]]*)\]", text, re.M)
    if m:
        items = [s.strip() for s in m.group(1).split(",") if s.strip()]
        if "differential" not in items:
            if "crash" in items:
                items.insert(items.index("crash") + 1, "differential")
            else:
                items.append("differential")
            new_line = "capability_set: [" + ", ".join(items) + "]"
            text = text[:m.start()] + new_line + text[m.end():]
            notes.append("cap+differential")
        else:
            notes.append("cap=ok")
    else:
        notes.append("NO-capability_set-line")

    # 2) provenance under target, right after the vuln_commit line.
    #    upstream fix -> fix_commit: <sha>;  strict fix -> fix_patch: <path>.
    field = "fix_patch" if patch else "fix_commit"
    val = patch if patch else sha
    if re.search(rf"^\s*{field}:", text, re.M):
        notes.append(f"{field}=ok")
    else:
        vm = re.search(r"^(\s*)vuln_commit:\s*\S.*$", text, re.M)
        if vm:
            indent = vm.group(1)
            comment = "   # no usable upstream fix; author-supplied root-cause guard" if patch else ""
            ins = f"\n{indent}{field}:   {val}{comment}"
            text = text[:vm.end()] + ins + text[vm.end():]
            notes.append(f"+{field}")
        else:
            notes.append("NO-vuln_commit-line")

    changed = text != orig
    return (changed, " ".join(notes)), text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    # Build the unified worklist: upstream-fix PASS/cached + strict-fix PASS.
    work = []  # (bug, sha, patch_or_None)
    upstream = {r["bug"] for r in RESULTS if r.get("status") in ("PASS", "cached")}
    for r in RESULTS:
        if r.get("status") in ("PASS", "cached"):
            work.append((r["bug"], r["sha"], None))
    for bug, r in STRICTFIX.items():
        if r.get("status") == "PASS" and bug not in upstream:
            work.append((bug, "", f"tools/fixes/{bug}.patch"))

    npass = nchanged = 0
    for bug, sha, patch in sorted(work):
        npass += 1
        d = bug_dir(bug)
        (changed, notes), text = edit_bench(d / "bench.yaml", sha, patch)
        if changed:
            nchanged += 1
            if a.write:
                (d / "bench.yaml").write_text(text)
        kind = "strict" if patch else "upstr "
        print(f"  {'WRITE' if (changed and a.write) else ('would' if changed else 'skip ')}  {kind} {bug:<44s} {notes}")
    print(f"\ndifferential bugs: {npass}  |  bench.yaml changed: {nchanged}  |  {'WRITTEN' if a.write else 'DRY-RUN (use --write)'}")


if __name__ == "__main__":
    main()
