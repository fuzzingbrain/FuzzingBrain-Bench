"""setup() surfaces the sanitizer (a fuzzing-setup fact) in EVERY mode, but never
the crash class (the answer).

setup() hands the model the sanitizer the build is judged under so the prompt can
state the real fault family instead of a fixed "memory-safety" framing. The
sanitizer is part of the fuzzing setup a real auditor always knows, so it is
given in normal, diff-scan, AND full-scan (full-scan's blindness is about WHAT /
WHERE the bug is, not the build's instrumentation). What must NEVER appear is the
specific class — expected.yaml class.expected.

Skipped when bin/mcp-server is not built (CI builds it first via `make`).
"""
import json
import tempfile

import pytest

from fbbench.grading import find_bug
from fbbench.paths import SERVER
from fbbench.runner.mcp_client import MCPClient, stage_bug_view

pytestmark = pytest.mark.skipif(not SERVER.exists(), reason="bin/mcp-server not built")

_BUG = "imagemagick-msl-stack-overflow"   # C/asan, class.expected = stack-overflow


def _setup(full_scan: bool) -> dict:
    real = str(find_bug(_BUG))
    view = stage_bug_view(real, full_scan=full_scan)
    ws = tempfile.mkdtemp()
    mcp = MCPClient(str(SERVER), bug_dir=view, workspace=ws, oracle_dir=real)
    try:
        mcp.initialize()
        return mcp.call("setup", {})
    finally:
        for closer in ("close", "stop", "terminate"):
            if hasattr(mcp, closer):
                try:
                    getattr(mcp, closer)()
                except Exception:
                    pass
                break


def test_normal_reveals_sanitizer():
    s = _setup(full_scan=False)
    assert s.get("sanitizer") == "asan"
    assert s.get("project") and s.get("language") == "c"


def test_fullscan_also_reveals_sanitizer():
    # The sanitizer is part of the fuzzing setup — given even in the blind tier.
    s = _setup(full_scan=True)
    assert s.get("sanitizer") == "asan", "full-scan must still surface the sanitizer"
    assert s.get("project") and s.get("language") == "c"


def test_setup_never_leaks_the_crash_class():
    # The sanitizer token is fine; the specific class answer must never appear in
    # the build facts (bug_desc legitimately describes the bug in normal mode, so
    # we check the structured facts, not the description).
    for fs in (False, True):
        s = _setup(full_scan=fs)
        facts = {k: s.get(k) for k in ("sanitizer", "project", "language",
                                       "capability_set")}
        assert "stack-overflow" not in json.dumps(facts), \
            f"full_scan={fs}: crash class leaked into setup() build facts"
