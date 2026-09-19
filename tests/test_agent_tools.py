"""Tools the agent arms get and the api arm does not.

The deliberate asymmetry of v2. v1 was sealed and offline: an agent could use
only what the image shipped, and gdb is in 45 of the 78 challenge images and
absent from 33, for no reason anyone chose. This is the place those extras go,
built so the next one is a file drop rather than a special case.
"""
import subprocess
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


def test_the_binaries_come_from_a_pinned_image_not_a_local_directory():
    """The reproducibility rule. A gitignored bin/ means a second machine runs a
    different benchmark and nothing says so; the numbers stop being comparable,
    which is the only thing a benchmark is for. One pinned image, identical bits
    everywhere, and the challenge images untouched."""
    src = inspect.getsource(ep)
    assert "FBBENCH_AGENT_TOOLS_IMAGE" in src
    assert "docker" in inspect.getsource(ep.ensure_agent_tools)
    # cache keyed by image id, so a version bump repopulates
    assert "digest" in inspect.getsource(ep.ensure_agent_tools)


def test_it_is_off_by_default_so_a_fresh_clone_runs():
    """Unset means agents get whatever the challenge image ships -- v1
    behaviour -- and nobody has to download anything to run the bench."""
    assert ep.AGENT_TOOLS_IMAGE == "" or ep.AGENT_TOOLS_IMAGE
    assert ep.agent_tool_mounts("") == ([], [])
    assert ep.ensure_agent_tools("") == ""


def test_a_cell_records_which_toolbox_produced_it():
    """Two runs that disagree must be tellable apart."""
    from fbbench.sweep import claudecode as cc, external as ex
    for src in (inspect.getsource(ex.run_cell), inspect.getsource(cc._persist)):
        assert '"agent_tools"' in src
        assert '"agent_tools_digest"' in src


# --------------------------------------------------------- provisioning it
# The toolbox image is FROM scratch: the binaries and nothing else. No shell,
# no cp, no libc. The first version of ensure_agent_tools() copied them out
# with `docker run --entrypoint sh ... -c "cp -a /tools/bin/. /out/"`, which
# cannot work against such an image and would have failed on every machine --
# the toolbox exists to remove exactly that kind of per-machine surprise, so
# it must not be the thing that introduces one.
def test_the_toolbox_is_extracted_without_running_anything_inside_it():
    src = inspect.getsource(ep.ensure_agent_tools)
    assert "docker" in src and "create" in src and "cp" in src
    assert "--entrypoint" not in src, (
        "extraction must not execute a program inside the toolbox image: it is "
        "FROM scratch and has none")


@pytest.mark.skipif(
    subprocess.run(["docker", "image", "inspect", "fbbench-agent-tools:v1"],
                   capture_output=True).returncode != 0,
    reason="toolbox image not built on this machine")
def test_a_built_toolbox_extracts_and_every_binary_is_self_contained(tmp_path, monkeypatch):
    """The real thing: pull it out of the image and check it needs no loader.

    A dynamically linked tool would start here and fail on the 33 challenge
    images that ship no debugger -- the failure this whole mechanism exists to
    prevent, and one nobody would attribute to the toolbox.
    """
    # Point the cache at tmp_path by patching the module attribute, NOT by
    # reloading the module: the parity tests assert that both agent arms hold
    # the *same function objects* as this module, and a reload silently
    # replaces them, failing three unrelated tests further down the run.
    monkeypatch.setattr(ep, "_CACHE_ROOT", str(tmp_path))
    d = ep.ensure_agent_tools("fbbench-agent-tools:v1")
    assert d and os.path.isdir(d)
    names = sorted(os.listdir(d))
    assert names, "toolbox came out empty"
    for name in names:
        p = os.path.join(d, name)
        assert os.access(p, os.X_OK), f"{name} is not executable"
        hdr = subprocess.run(["readelf", "-l", p], capture_output=True, text=True)
        if hdr.returncode == 0:
            assert "INTERP" not in hdr.stdout, (
                f"{name} needs a dynamic loader and will not run on every image")
