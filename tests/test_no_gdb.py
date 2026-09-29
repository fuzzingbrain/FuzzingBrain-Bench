"""--no-gdb: the same setting with only the debugger taken away."""
import os

from fbbench import sandbox
from fbbench.sweep.mcp_episode import ORACLE_HARNESS, agent_tools_note


def test_off_by_default(monkeypatch):
    monkeypatch.delenv(sandbox.NO_GDB_ENV, raising=False)
    assert not sandbox.no_gdb()
    assert not any("gdb-unavailable" in a for a in sandbox.sandbox_args())


def test_the_debugger_is_replaced_in_the_container(monkeypatch):
    monkeypatch.setenv(sandbox.NO_GDB_ENV, "1")
    args = sandbox.sandbox_args()
    for p in ("/usr/bin/gdb", "/usr/bin/gdbtui"):
        assert f"{sandbox.GDB_STUB}:{p}:ro" in args
    assert os.access(sandbox.GDB_STUB, os.X_OK)


def test_the_note_changes_only_the_gdb_sentences():
    t = ORACLE_HARNESS
    with_gdb = agent_tools_note({"gdb": True, "native": True, "target": t})
    without = agent_tools_note({"gdb": False, "native": True, "target": t})
    assert "gdb" in with_gdb and "gdb" not in without
    # the run and coverage guidance is identical in both
    for part in (f"Run it on an input file (`{t} /workspace/in`)",
                 "a directory without `-runs=0` is treated as fuzzing and refused",
                 f'{t} -runs=0 -print_coverage=1 "$d"',
                 "an input that crashes stops before the report",
                 "run it again."):
        assert part in with_gdb and part in without, part


def test_java_targets_are_unchanged():
    """No gdb and no coverage recipe was ever offered on a JVM harness."""
    t = ORACLE_HARNESS
    assert agent_tools_note({"gdb": False, "native": False, "target": t}).startswith(
        "- You may also read and run the binary")
