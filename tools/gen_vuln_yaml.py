#!/usr/bin/env python3
"""Generate per-bug vuln.yaml — HIDDEN ground-truth metadata.

vuln.yaml records the vulnerability classification + analysis metadata that
must NOT reach the agent (category == the T2 class answer). It is deliberately
kept OUT of mcp_client.SANDBOX_ENTRIES, so the allowlist staging never copies it
into the agent's view (fail-safe: hidden by default).

Mechanically-derivable fields are filled from the existing single sources of
truth (grader/expected.yaml, bench.yaml); `difficulty` and a few CWEs are left
for the human passes (issues #11 / #12). Re-run any time; only changed files are
rewritten.

Usage:
    PYTHONPATH=.:tools python tools/gen_vuln_yaml.py            # all bugs
    PYTHONPATH=.:tools python tools/gen_vuln_yaml.py --check    # diff only
"""
from __future__ import annotations

import argparse
import os
import sys

import yaml

from fbbench.paths import REPO

# Bugs to park via active:false. Empty for now — the whole corpus ships active;
# the `active` switch + run/grade/sweep filtering is wired up and ready, so any
# bug can be parked later by adding it here (or editing its vuln.yaml). The
# cross-repo third-party-lib bugs (jsoncpp/graal/skia) are the likely first
# candidates once their modelling is settled — see issue #14.
DEACTIVATED: set[str] = set()

# Controlled vocabulary for `category` — the ONLY allowed values (plus the
# "unclassified" placeholder). The semantic vulnerability TYPE, NOT the sanitizer
# crash class: `segv`/`abrt` are symptoms that map to several of these. Locked;
# document in docs/SPEC.md. Add a term here (and to SPEC) before using it.
CANONICAL_CATEGORIES = {
    # memory-safety — spatial
    "heap-buffer-overflow", "stack-buffer-overflow", "stack-buffer-underflow",
    "out-of-bounds-read", "out-of-bounds-write",
    # memory-safety — temporal / pointer
    "use-after-free", "null-pointer-dereference",
    # resource / DoS
    "memory-leak", "memory-exhaustion", "excessive-computation", "stack-exhaustion",
    # logic / language
    "reachable-assertion", "type-confusion", "uncaught-exception",
    "undefined-behavior",
}
UNCLASSIFIED = "unclassified"

# Canonical language notation: c / cpp / jvm (OSS-Fuzz uses `jvm`; we use `cpp`).
_LANG_CANON = {"c++": "cpp", "java": "jvm"}

# Fixing commit, where known (not recorded upstream for most). Add as discovered;
# bugs absent here get `fix_commit: null`.
_FIX_COMMIT = {
    "skia-raster8888-blur-oob": "d2740c899a1ec8a22209840bd8350f22f8c27ecf",  # CL 1225736 (see NOTES.md)
}

# Crash class -> canonical category, but ONLY where the crash class is itself
# self-describing (the type == the symptom). Symptom-only classes (segv, abrt,
# abort, uncaught-exception, out-of-bounds-access, empty) are deliberately absent
# -> they resolve to `unclassified` and get a per-bug code-reading pass (#12),
# because e.g. a `segv` may be a null-deref, a UAF, or an OOB read.
# Per-bug categories established by READING the root-cause code (the #12 pass) —
# authoritative, overrides the crash-class map. Used for symptom classes (segv/
# abrt/uncaught-exception/empty) where the crash class doesn't reveal the type.
# Each is grounded in the reach/site source (see commit / PR notes).
_CURATED = {
    "avro-neg-string-len":            "out-of-bounds-read",      # negative key_size -> OOB string read
    "graal-regexlexer-oob":           "out-of-bounds-read",      # pattern.charAt(position) no bounds check
    "graaljs-illformed-locale":       "uncaught-exception",      # IllformedLocaleException from Locale.Builder
    "icu-translit-rule-dtor-uaf":     "use-after-free",          # dtor frees pointers of a partial rule
    "imagemagick-kernelinfo-alloc":   "memory-exhaustion",       # excessive AcquireKernelInfo allocation
    "imagemagick-msl-comment-npd":    "null-pointer-dereference",  # msl_info->image[n] NULL deref
    "jq-dump-op-npd":                 "null-pointer-dereference",  # getlevel()->subfunctions[idx] NULL
    "jsonjava-unescape-numformat":    "uncaught-exception",      # NumberFormatException
    "libaom-av1-config-assert":       "reachable-assertion",     # assert in aom_rb_read_literal
    "libvpx-vp9-encoder-caq-assert":  "reachable-assertion",     # VP9 CAQ assertion
    "libwebp-muxassemble-npd":        "null-pointer-dereference",  # data->bytes NULL deref
    "libwebp-sharpyuv-convert-stride-oob": "out-of-bounds-read",  # missing stride validation -> OOB read
    "libwebp-sharpyuv-gamma-oob":     "out-of-bounds-read",      # unclamped LUT index -> OOB read
    "ndpi-hex-decode-sscanf":         "out-of-bounds-read",      # sscanf reads past borrowed src buffer
    "netsnmp-vacm-parse-npd":         "null-pointer-dereference",  # skip_token_const()->NULL then deref
    "opcua-pubsub-json-assert":       "reachable-assertion",     # lookAheadForKey assertion
    "openscreen-jsoncpp-nonobject-oob": "reachable-assertion",   # jsoncpp find() JSON_ASSERT abort
    "ots-processgeneric-npd":         "null-pointer-dereference",  # maxp NULL deref
    "pdfbox-pfb-negative-array":      "uncaught-exception",      # NegativeArraySizeException
    "skia-raster8888-blur-oob":       "out-of-bounds-read",      # eval_blur_passes OOB pixel pointer (read)
    "spirv-orderblocks-segv":         "null-pointer-dereference",  # blocks[0] on empty CFG -> null data deref
    "systemd-hwdb-trie-oob-read":     "out-of-bounds-read",      # trie offset deref before bounds check
}

_CONFIDENT_MAP = {
    "heap-buffer-overflow":    "heap-buffer-overflow",
    "heap-use-after-free":     "use-after-free",
    "use-after-free":          "use-after-free",
    "stack-buffer-overflow":   "stack-buffer-overflow",
    "stack-buffer-underflow":  "stack-buffer-underflow",
    "stack-overflow":          "stack-exhaustion",
    "oob-read":                "out-of-bounds-read",
    "memory-leak":             "memory-leak",
    "oom":                     "memory-exhaustion",
    "allocation-size-too-big": "memory-exhaustion",
    "timeout":                 "excessive-computation",
    "undefined-behavior":      "undefined-behavior",
    "misaligned-access":       "undefined-behavior",
    "class-cast":              "type-confusion",
}

_HEADER = (
    "# vuln.yaml — HIDDEN ground-truth metadata. NOT in SANDBOX_ENTRIES, so it is\n"
    "# never staged into the agent's view. `category` is the T2 class answer — do\n"
    "# not move it into an agent-visible file. Generated by tools/gen_vuln_yaml.py;\n"
    "# `sanitizer`/`vuln_version` mirror their source-of-truth in\n"
    "# grader/expected.yaml + bench.yaml (regenerate rather than hand-editing those).\n"
    "# `difficulty` and `category` refinement are the human passes (#11 / #12).\n"
)


def _iter_bug_dirs(one: str | None):
    for proj in sorted(os.listdir(REPO / "bugs")):
        proj_dir = REPO / "bugs" / proj
        if not proj_dir.is_dir():
            continue
        for name in sorted(os.listdir(proj_dir)):
            d = proj_dir / name
            if (d / "bench.yaml").is_file() and (not one or name == one):
                yield str(d)


def _compute(bug_dir: str) -> dict:
    bug = os.path.basename(bug_dir)
    bench = yaml.safe_load(open(os.path.join(bug_dir, "bench.yaml"))) or {}
    tgt = bench.get("target", {}) or {}
    exp = {}
    exp_path = os.path.join(bug_dir, "grader", "expected.yaml")
    if os.path.exists(exp_path):
        exp = yaml.safe_load(open(exp_path)) or {}
    cls = (exp.get("class") or {})
    raw = cls.get("expected") or ""
    # curated (code-verified) wins; else the self-describing crash class; else
    # unclassified.
    category = _CURATED.get(bug) or _CONFIDENT_MAP.get(raw, UNCLASSIFIED)
    assert category in CANONICAL_CATEGORIES or category == UNCLASSIFIED, \
        f"{bug}: category {category!r} not in the controlled vocabulary"
    return {
        "category": category,
        "difficulty": "none",
        "metadata": {
            "language": _LANG_CANON.get(tgt.get("language"), tgt.get("language") or None),
            "arch": "x86_64",   # whole corpus targets x86_64 Linux (the prebuilt
                                # binaries); override per bug if that ever changes
            "sanitizer": cls.get("sanitizer") or None,
            "vuln_version": tgt.get("vuln_commit") or None,
            "fix_commit": _FIX_COMMIT.get(bug),   # null where not recorded
        },
        "active": bug not in DEACTIVATED,
    }


def _dump(payload: dict) -> str:
    return _HEADER + yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate per-bug vuln.yaml")
    ap.add_argument("--bug")
    ap.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = ap.parse_args()

    wrote = unchanged = drift = 0
    for bug_dir in _iter_bug_dirs(args.bug):
        bug = os.path.basename(bug_dir)
        text = _dump(_compute(bug_dir))
        out = os.path.join(bug_dir, "vuln.yaml")
        old = open(out).read() if os.path.exists(out) else None
        if old == text:
            unchanged += 1
            continue
        if args.check:
            drift += 1
            print(f"DRIFT {bug}")
            continue
        with open(out, "w") as fp:
            fp.write(text)
        wrote += 1
        print(f"WROTE {bug}  ({'INACTIVE' if bug in DEACTIVATED else 'active'})")

    if args.check:
        print(f"\ncheck: {unchanged} unchanged, {drift} drift")
        return 1 if drift else 0
    print(f"\nvuln.yaml: {wrote} written, {unchanged} unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
