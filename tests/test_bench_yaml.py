"""bench.yaml reading + bug discovery."""
import os
import shutil

from fbbench.grading import (
    capability_set, find_bug, is_active, list_bugs, read_bench,
)


def test_list_bugs_nonempty():
    bugs = list_bugs()
    assert len(bugs) >= 30
    assert "netsnmp-vacm-parse-npd" in [b for b, _ in bugs]


def test_capability_set_is_a_ladder_subset():
    bd = find_bug("netsnmp-vacm-parse-npd")
    assert bd is not None
    kb = capability_set(bd)
    assert kb and set(kb) <= {"reach", "crash", "class", "site"}


def test_read_bench_scalars():
    bd = find_bug("netsnmp-vacm-parse-npd")
    bench = read_bench(bd / "bench.yaml")
    assert bench.get("bug_id") == "netsnmp-vacm-parse-npd"


def test_find_bug_missing_returns_none():
    assert find_bug("does-not-exist") is None


def test_is_active_default_true():
    bd = find_bug("netsnmp-vacm-parse-npd")
    assert is_active(bd) is True


def test_list_bugs_excludes_inactive():
    """list_bugs() defaults to active-only; include_inactive is a superset."""
    active = {b for b, _ in list_bugs()}
    every = {b for b, _ in list_bugs(include_inactive=True)}
    assert active <= every  # never returns a parked bug the all-set lacks


def test_vuln_yaml_category_in_controlled_vocabulary():
    """Every vuln.yaml category is a locked canonical term (or `unclassified`)."""
    import sys

    from fbbench.paths import REPO
    sys.path.insert(0, str(REPO / "tools"))
    from gen_vuln_yaml import CANONICAL_CATEGORIES, UNCLASSIFIED

    allowed = CANONICAL_CATEGORIES | {UNCLASSIFIED}
    bad = []
    for bug, d in list_bugs(include_inactive=True):
        vp = d / "vuln.yaml"
        if not vp.is_file():
            continue
        cat = read_bench(vp).get("category")
        if cat not in allowed:
            bad.append((bug, cat))
    assert not bad, f"categories outside the controlled vocabulary: {bad}"


def test_vuln_yaml_never_staged_to_agent():
    """vuln.yaml holds the hidden class answer; it must never reach the agent.

    The staging allowlist (SANDBOX_ENTRIES) is the structural guarantee — assert
    it here so a future entry added to that list can't silently leak vuln.yaml.
    """
    from fbbench.runner.mcp_client import stage_bug_view

    bd = find_bug("netsnmp-vacm-parse-npd")
    assert (bd / "vuln.yaml").is_file()  # the bug actually has one to leak
    os.environ["BENCH_STAGE_SOURCE"] = "0"  # skip the network source clone
    view = stage_bug_view(str(bd), full_scan=False)
    try:
        assert "vuln.yaml" not in os.listdir(view)
    finally:
        shutil.rmtree(view, ignore_errors=True)
