"""--no-debugging-tool: the same setting with only the debugger taken away.

The debugger is gdb on a native target and jdb (through jdb-run) on a JVM one;
no challenge has both.
"""
import os
from pathlib import Path

from fbbench import sandbox
from fbbench.sweep.mcp_episode import ORACLE_HARNESS, agent_tools_note, debugger_offered

ROOT = Path(__file__).resolve().parent.parent


def test_off_by_default(monkeypatch):
    monkeypatch.delenv(sandbox.NO_DEBUGGING_TOOL_ENV, raising=False)
    assert not sandbox.no_debugging_tool()
    assert not any("debugging-tool-unavailable" in a for a in sandbox.sandbox_args())


def test_every_debugger_is_replaced_in_the_container(monkeypatch):
    monkeypatch.setenv(sandbox.NO_DEBUGGING_TOOL_ENV, "1")
    args = sandbox.sandbox_args()
    for p in ("/usr/bin/gdb", "/usr/bin/gdbtui", "/usr/bin/jdb", "/usr/local/bin/jdb-run"):
        assert f"{sandbox.DEBUGGER_STUB}:{p}:ro" in args
    assert os.access(sandbox.DEBUGGER_STUB, os.X_OK)


def test_old_flag_name_still_parses():
    from fbbench.cli.main import build_parser
    p = build_parser()
    for flag in ("--no-debugging-tool", "--no-gdb"):
        a = p.parse_args(["run", "json-java-02", flag])
        assert a.no_debugging_tool


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


def test_java_without_a_debugger_is_unchanged():
    """No gdb and no coverage recipe was ever offered on a JVM harness."""
    t = ORACLE_HARNESS
    assert agent_tools_note({"gdb": False, "native": False, "target": t}) == (
        f"- You may also read and run the binary run_poc_on_harness() grades against, at {t}.")


def test_java_note_adds_only_the_jdb_sentences():
    t = ORACLE_HARNESS
    without = agent_tools_note({"jdb": False, "native": False, "target": t})
    with_jdb = agent_tools_note({"jdb": True, "native": False, "target": t})
    assert with_jdb.startswith(without + " ")
    assert "jdb-run -ex run -ex where /workspace/in" in with_jdb
    assert "gdb -batch" in with_jdb and "`gdb`" not in with_jdb


def test_jdb_is_never_offered_on_a_native_target():
    t = ORACLE_HARNESS
    note = agent_tools_note({"gdb": False, "jdb": True, "native": True, "target": t})
    assert "jdb" not in note


def test_the_cell_records_which_debugger():
    assert debugger_offered({"gdb": True}) == "gdb"
    assert debugger_offered({"jdb": True}) == "jdb"
    assert debugger_offered({}) == "" and debugger_offered(None) == ""


def test_jdb_image_layer_pins_the_jre():
    """The JDK must come from the image's own JRE build, or the graded JVM changes."""
    df = (ROOT / "tools/jdb/Dockerfile").read_text()
    assert "openjdk-17-jdk-headless=${JDK_VERSION}" in df
    assert df.count("dpkg-query -W -f='${Version}' openjdk-17-jre-headless") == 2
    assert os.access(ROOT / "tools/jdb/jdb-run", os.X_OK)
