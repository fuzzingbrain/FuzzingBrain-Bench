"""The sanitizer is revealed in normal/diff-scan but WITHHELD in full-scan.

setup() now hands the model the sanitizer the build is judged under (so the
prompt can state the real fault family instead of a fixed "memory-safety"
framing). The sanitizer names the fault FAMILY, so full-scan — the blind tier,
which already scrubs capability_set for exactly this reason — must NOT receive
it. This guards that BENCH_TASK_MODE gating end-to-end, and that setup() never
leaks the actual crash class (expected.yaml class.expected).

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


def _setup(task_mode: str, full_scan: bool) -> dict:
    real = str(find_bug(_BUG))
    view = stage_bug_view(real, full_scan=full_scan)
    ws = tempfile.mkdtemp()
    mcp = MCPClient(str(SERVER), bug_dir=view, workspace=ws, oracle_dir=real,
                    task_mode=task_mode)
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
    s = _setup("normal", full_scan=False)
    assert s.get("sanitizer") == "asan"
    assert s.get("project") and s.get("language") == "c"


def test_diffscan_reveals_sanitizer():
    # diff-scan reuses full-scan staging but DOES reveal the sanitizer.
    s = _setup("diffscan", full_scan=True)
    assert s.get("sanitizer") == "asan"


def test_fullscan_withholds_sanitizer():
    s = _setup("fullscan", full_scan=True)
    assert "sanitizer" not in s, "full-scan leaked the sanitizer (fault family)"
    # project/language are public build facts and stay.
    assert s.get("project") and s.get("language") == "c"


def test_setup_never_leaks_the_crash_class():
    # The sanitizer token is fine; the specific class answer must never appear.
    for mode, fs in (("normal", False), ("diffscan", True), ("fullscan", True)):
        s = _setup(mode, fs)
        # bug_desc legitimately describes the bug in normal mode; check the build
        # facts we added, not the description, for the class token.
        facts = {k: s.get(k) for k in ("sanitizer", "project", "language",
                                       "capability_set")}
        assert "stack-overflow" not in json.dumps(facts), \
            f"{mode}: crash class leaked into setup() build facts"
