"""Tools the agent arms get and the api arm does not.

The deliberate asymmetry of v2. v1 was sealed and offline: an agent could use
only what the image shipped, and gdb is in 45 of the 78 challenge images and
absent from 33, for no reason anyone chose. This is the place those extras go,
built so the next one is a file drop rather than a special case.
"""
import inspect
import os
import stat

import pytest

from fbbench.sweep import mcp_episode as ep


@pytest.fixture
def toolbox(tmp_path):
    d = tmp_path / "bin"; d.mkdir()
    for name in ("gdb", "strace"):
        f = d / name; f.write_text("#!/bin/sh\n"); f.chmod(f.stat().st_mode | stat.S_IXUSR)
    (d / "notes.md").write_text("not executable")       # ignored
    (d / "mcp-server").write_bytes(b"x"); (d / "mcp-server").chmod(0o755)   # reserved
    return d


def test_each_executable_is_mounted_onto_the_path(toolbox):
    args, names = ep.agent_tool_mounts(str(toolbox))
    assert names == ["gdb", "strace"]
    assert args == ["-v", f"{toolbox}/gdb:/usr/local/bin/gdb:ro",
                    "-v", f"{toolbox}/strace:/usr/local/bin/strace:ro"]


def test_the_image_s_own_binaries_are_never_shadowed(toolbox):
    """/usr/local/bin holds mcp-server and llvm-symbolizer. Mounting over them
    breaks the episode in a way that looks like the agent's fault -- which is
    also why these are mounted file by file and never as a directory."""
    _, names = ep.agent_tool_mounts(str(toolbox))
    assert "mcp-server" not in names
    assert "-v" in inspect.getsource(ep.agent_tool_mounts)
    src = inspect.getsource(ep._start_episode_server)
    assert "/usr/local/bin\"" not in src, "a directory mount would hide the server"


def test_a_checkout_with_no_binaries_still_runs(tmp_path):
    """Empty or missing is fine: agents then have whatever the image ships,
    which is exactly v1 behaviour. A clone must not need a 100MB download."""
    assert ep.agent_tool_mounts(str(tmp_path / "nope")) == ([], [])
    (tmp_path / "empty").mkdir()
    assert ep.agent_tool_mounts(str(tmp_path / "empty")) == ([], [])


def test_only_the_agent_arms_mount_them():
    """The api arm starts its own container through MCPClient and must be
    untouched -- by construction, not by a flag anyone has to remember."""
    from fbbench.runner import mcp_client
    assert "agent_tool_mounts" not in inspect.getsource(mcp_client)
    assert "agent_tool_mounts" in inspect.getsource(ep._start_episode_server)


def test_both_arms_record_what_was_available():
    """A result should be readable knowing which tools were on PATH."""
    from fbbench.sweep import claudecode as cc, external as ex
    assert '"agent_tools"' in inspect.getsource(ex.run_cell)
    assert '"agent_tools"' in inspect.getsource(cc._persist)


def test_the_directory_is_overridable_for_large_binaries():
    """Static debuggers are tens of megabytes and do not belong in a clone."""
    assert "FBBENCH_AGENT_TOOLS" in inspect.getsource(ep)
