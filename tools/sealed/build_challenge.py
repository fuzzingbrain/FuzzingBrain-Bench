#!/usr/bin/env python3
"""Build a sealed CHALLENGE image for one bug — public, answer-free.

The image bakes exactly what `stage_bug_view()` exposes (src@vuln_commit, harness,
description.txt, scrubbed bench.yaml) plus the mcp-server client. grade() is wired
to a remote oracle via BENCH_GRADE_URL; the image contains NO poc / expected.yaml /
binaries / fix_commit. A leak audit asserts this before the build.

Usage:
  build_challenge.py <bug_id> [--grade-url URL] [--tag-prefix fbbench-challenge] [--no-build]
"""
from __future__ import annotations
import argparse, os, shutil, subprocess, sys, tempfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from fbbench.grading.bench_yaml import find_bug          # noqa: E402
from fbbench.runner.mcp_client import stage_bug_view, _full_scan_alias  # noqa: E402

# A bug's OWN answer artifacts — these must never appear in a challenge image.
ANSWER_NAMES = ("poc", "grader", "binaries")
ANSWER_SUFFIX = ("expected.yaml",)

def leak_audit(bundle: Path) -> list[str]:
    leaks = []
    for p in bundle.rglob("*"):
        rel = p.relative_to(bundle)
        parts = rel.parts
        # Only the bundle's TOP-LEVEL answer dirs are leaks; src/** is upstream
        # source (may legitimately contain *.bin test fixtures, expected.yaml in
        # the project's own tests, etc.) and is public by design.
        if parts and parts[0] == "src":
            continue
        if any(seg in ANSWER_NAMES for seg in parts):
            leaks.append(str(rel))
        elif p.name in ANSWER_SUFFIX:
            leaks.append(str(rel))
    # bench.yaml must not carry fix_commit / fix_patch
    by = bundle / "bench.yaml"
    if by.exists():
        b = yaml.safe_load(by.read_text()) or {}
        tgt = b.get("target", {}) or {}
        if tgt.get("fix_commit") or tgt.get("fix_patch"):
            leaks.append("bench.yaml:fix_commit/fix_patch")
    return leaks

DOCKERFILE = """# syntax=docker/dockerfile:1.6
# Sealed CHALLENGE image for {bug} — public, answer-free.
# Contains source@vuln_commit + harness + the mcp-server client. grade() proxies
# to the remote oracle (BENCH_GRADE_URL); NO answer key is present.
FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \\
        clang libclang-rt-14-dev build-essential ca-certificates python3 \\
    && rm -rf /var/lib/apt/lists/*
WORKDIR /challenge
COPY bundle/ /challenge/
COPY mcp-server /usr/local/bin/mcp-server
RUN mkdir -p /workspace && chmod 0777 /workspace
ENV BENCH_BUG_ID={bug}
ENV BENCH_GRADE_URL={grade_url}
ENV BENCH_BUG_DIR=/challenge
ENV BENCH_WORKSPACE=/workspace
# Self-driveable: `docker run -i <image> mcp-server` speaks the stdio MCP protocol
# (setup/read/list/write/exec/grade) with everything baked in — this is the single
# canonical runtime for the benchmark, identical for us and any external user.
# grade() is a network call to BENCH_GRADE_URL; everything else is local to the image.
LABEL fbbench.role="challenge" fbbench.bug="{bug}"
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bug_id")
    ap.add_argument("--grade-url", default="http://host.docker.internal:8077")
    ap.add_argument("--tag-prefix", default="fbbench-challenge")
    ap.add_argument("--no-build", action="store_true")
    # The PUBLIC image is ALWAYS the NEUTRAL (discovery) view: no description
    # naming the bug, scrubbed bench.yaml, neutralized harness. The rich normal
    # (hinted) view leaks the description, so it is intentionally NOT available in
    # this public repo — it exists only in the private answers repo, for internal
    # use. full_scan is therefore forced on here; `--full-scan` is kept as an
    # accepted no-op for backward compatibility.
    ap.add_argument("--full-scan", dest="full_scan", action="store_true", default=True,
                    help=argparse.SUPPRESS)
    a = ap.parse_args()

    bug_dir = find_bug(a.bug_id, ROOT)
    if bug_dir is None:
        print(f"error: bug {a.bug_id} not found", file=sys.stderr); return 2

    # The PUBLIC handle is the NEUTRAL alias (<project>-NN), never the descriptive
    # bug_id: the image tag + BENCH_BUG_ID land in a crawlable registry, so the
    # descriptive name (which spells out the fault) would itself name the bug. The
    # operator still passes the descriptive id (to locate the bug); the alias is
    # used for the tag + the oracle key. The alias<->bug map lives oracle-side.
    alias = _full_scan_alias(str(bug_dir))

    ctx = Path(tempfile.mkdtemp(prefix=f"fbchal-{alias}-"))
    bundle_src = Path(stage_bug_view(str(bug_dir), full_scan=a.full_scan))
    bundle = ctx / "bundle"
    # symlinks=True is CRITICAL: never dereference. Upstream source trees contain
    # directory symlinks (e.g. graal-nodejs, vendored node_modules) and some point
    # at ancestors — dereferencing recurses and balloons a bundle to tens of GB.
    # Preserve symlinks as-is; docker COPY tars them without following either.
    shutil.copytree(bundle_src, bundle, symlinks=True, ignore_dangling_symlinks=True)
    shutil.rmtree(bundle_src, ignore_errors=True)

    leaks = leak_audit(bundle)
    if leaks:
        print(f"*** LEAK AUDIT FAILED for {a.bug_id}: {leaks}", file=sys.stderr)
        shutil.rmtree(ctx, ignore_errors=True); return 3
    print(f"[{a.bug_id}] leak audit CLEAN ({sum(1 for _ in bundle.rglob('*'))} files in bundle)")

    shutil.copy2(ROOT / "bin" / "mcp-server", ctx / "mcp-server")
    # BENCH_BUG_ID = alias: the challenge POSTs /grade?bug=<alias>; the oracle keys
    # its bundle by the same alias (oracle-root/<alias>).
    (ctx / "Dockerfile").write_text(DOCKERFILE.format(bug=alias, grade_url=a.grade_url))

    tag = f"{a.tag_prefix}/{alias}:latest"
    if a.no_build:
        print(f"[{a.bug_id} -> {alias}] context ready at {ctx} (skipped build); tag would be {tag}")
        return 0
    print(f"[{a.bug_id} -> {alias}] docker build -> {tag}")
    r = subprocess.run(["docker", "build", "-t", tag, str(ctx)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:], file=sys.stderr)
        shutil.rmtree(ctx, ignore_errors=True); return 4
    shutil.rmtree(ctx, ignore_errors=True)
    print(f"[{a.bug_id} -> {alias}] BUILT {tag}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
