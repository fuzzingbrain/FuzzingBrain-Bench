"""bench.yaml reading + bug discovery, with no external YAML dependency.

bench.yaml top-levels we need (title, project, capability_set, ...) are flat
scalars or one-line [lists], so a tiny ad-hoc reader avoids pulling PyYAML
into the stdlib-only CLI path. This replaces the four near-identical readers
that used to live in fb-bench, the runner, and the sweep scripts.
"""
from __future__ import annotations

from pathlib import Path

from fbbench.paths import REPO

DEFAULT_KB = ["reach", "crash", "class", "site"]


def read_bench(path: Path) -> dict:
    """Parse a bench.yaml's top-level scalars and one-line [lists]."""
    out: dict = {}
    for line in Path(path).read_text().splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line or ":" not in line or line[0] in " \t-":
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            out[k.strip()] = [s.strip().strip("\"'") for s in v[1:-1].split(",") if s.strip()]
        else:
            out[k.strip()] = v.strip("\"'")
    return out


def capability_set(bug_dir: Path) -> list[str]:
    """K_b (required flags) for a bug, or the full default ladder if unset."""
    kb = read_bench(Path(bug_dir) / "bench.yaml").get("capability_set")
    return kb if isinstance(kb, list) and kb else list(DEFAULT_KB)


def find_bug(bug_id: str, repo: Path = REPO) -> Path | None:
    """Absolute path to bugs/*/<bug_id>, or None if there is no such bug.

    Finds parked (active:false) bugs too, so an explicit `grade`/`run <id>` still
    works; only the bulk enumeration in list_bugs() skips inactive bugs.
    """
    for proj in (repo / "bugs").iterdir():
        if proj.is_dir() and (proj / bug_id).is_dir():
            return proj / bug_id
    return None


def is_active(bug_dir: Path) -> bool:
    """Whether a bug is part of the active corpus.

    A bug is inactive only if its vuln.yaml sets `active: false` (e.g. a parked
    third-party-lib bug). Missing vuln.yaml or missing field => active. `active`
    is a flat top-level scalar, so the stdlib reader handles it (no PyYAML).
    """
    p = Path(bug_dir) / "vuln.yaml"
    if not p.is_file():
        return True
    v = read_bench(p).get("active", "true")
    return str(v).strip().lower() not in ("false", "no", "0", "off")


def list_bugs(repo: Path = REPO, include_inactive: bool = False) -> list[tuple[str, Path]]:
    """Active shippable bugs: (bug_id, dir) with bench.yaml + binaries/.

    Parked bugs (vuln.yaml `active: false`) are skipped unless include_inactive,
    so list / grade-all / sweep only ever touch the active corpus.
    """
    bugs: list[tuple[str, Path]] = []
    for proj in sorted((repo / "bugs").iterdir()):
        if not proj.is_dir():
            continue
        for sub in sorted(proj.iterdir()):
            if (sub / "bench.yaml").is_file() and (sub / "binaries").is_dir():
                if include_inactive or is_active(sub):
                    bugs.append((sub.name, sub))
    return bugs
