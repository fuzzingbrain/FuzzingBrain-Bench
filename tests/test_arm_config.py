# SPDX-License-Identifier: Apache-2.0
"""The Claude Code arm's launch configuration, checked without spending a cent.

`test_no_cheat.py` proves the real property — that the arm cannot read the
sealed answers off the host — but it can only prove it by driving the actual
`claude` CLI, because the containment is enforced by the CLI's permission layer
and not by the OS. A scripted attacker would simply `open()` the canary and
"fail" a test the shipped arm passes. So that proof costs money every run, and
in practice it is run rarely.

This file covers the half that is free, and it is the half that actually broke:
#120 changed `stage_claude_env`'s return arity and left its one external caller
unpatched, so `test_no_cheat.py` died on a ValueError before it ever reached a
model. The security property was fine; the call contract was not, and nothing
noticed for as long as it took someone to run the script by hand.

What is asserted here is everything about the launch that can be read off the
argv, the environment and the source: the hardening flags are present, the
denylist still names every built-in that could reach the host, the allowlist is
bench-MCP-only, and the environment handed to `claude` carries nothing but PATH
and HOME. If one of these regresses, the live proof would fail too — but this
fails in milliseconds, for free, in CI.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

import pytest

from fbbench.sweep import claudecode as cc


# Built-ins that would let an agent reach the host filesystem, the network, or a
# shell. Any of these slipping out of the denylist is the regression that
# `test_no_cheat.py` exists to catch, so name them explicitly rather than
# comparing against the module's own constant (which would pass trivially).
MUST_DENY = (
    "Bash", "BashOutput", "KillShell", "Read", "Write", "Edit", "MultiEdit",
    "NotebookEdit", "Glob", "Grep", "Task", "Agent", "WebFetch", "WebSearch",
    "ToolSearch", "TodoWrite", "Skill", "SlashCommand", "ExitPlanMode",
)


@pytest.fixture
def argv():
    return cc.claude_cmd("PROMPT", "/tmp/cell/bench.mcp.json", "haiku", max_turns=6)


def _flag(argv, name):
    return argv[argv.index(name) + 1]


# ------------------------------------------------------------ the call contract

def test_stage_claude_env_returns_what_its_callers_unpack():
    """The exact break from #120: the return grew, the callers did not.

    Parsed rather than counted -- the last element is itself a tuple, so a comma
    count says 5 separators where there are 4.
    """
    tree = ast.parse(textwrap.dedent(inspect.getsource(cc.stage_claude_env)))
    rets = [n for n in ast.walk(tree)
            if isinstance(n, ast.Return) and n.value is not None]
    final = rets[-1].value
    assert isinstance(final, ast.Tuple), "stage_claude_env returns a tuple"
    assert len(final.elts) == 5, "image, root, work, mcp_cfg, (server, srv_sock)"
    assert isinstance(final.elts[-1], ast.Tuple), "the relay comes back as a pair"


def _unpack_widths(path):
    """(line, n) for every `... = stage_claude_env(...)` assignment in a file.

    Parsed, not counted: `a, b, c, d, (e, f)` has five commas and four
    separators, which is exactly the trap that makes a hand-rolled check wrong.
    """
    try:
        tree = ast.parse(path.read_text(errors="ignore"))
    except SyntaxError:
        return []
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        fn = node.value.func
        name = getattr(fn, "id", None) or getattr(fn, "attr", None)
        if name != "stage_claude_env":
            continue
        tgt = node.targets[0]
        out.append((node.lineno, len(tgt.elts) if isinstance(tgt, ast.Tuple) else 1))
    return out


def test_every_caller_unpacks_the_relay():
    """A caller that drops the relay leaks a process and a socket per cell."""
    import pathlib
    root = pathlib.Path(cc.__file__).resolve().parents[2]
    found = []
    for path in root.rglob("*.py"):
        for lineno, width in _unpack_widths(path):
            found.append((path.name, lineno, width))
    assert found, "the function has callers; the search found none"
    bad = [f for f in found if f[2] != 5]
    assert not bad, f"callers that do not unpack 5: {bad}"


# ------------------------------------------------------------- hardening flags

@pytest.mark.parametrize("flag", [
    "--mcp-config", "--strict-mcp-config", "--allowedTools",
    "--disallowedTools", "--permission-mode", "--setting-sources",
])
def test_the_hardening_flag_is_present(argv, flag):
    assert flag in argv


def test_settings_come_only_from_the_project(argv):
    """`user` or `local` would let the host's own Claude settings widen the arm."""
    assert _flag(argv, "--setting-sources") == "project"


def test_permission_mode_is_not_bypassed(argv):
    mode = _flag(argv, "--permission-mode")
    assert mode == "default"
    assert "--dangerously-skip-permissions" not in argv


# ------------------------------------------------------------------ tool lists

@pytest.mark.parametrize("tool", MUST_DENY)
def test_the_denylist_still_names(argv, tool):
    assert tool in _flag(argv, "--disallowedTools").split(",")


def test_only_bench_mcp_tools_are_allowed(argv):
    allowed = _flag(argv, "--allowedTools").split(",")
    assert allowed, "an empty allowlist would leave the arm unable to work"
    off = [t for t in allowed if not t.startswith("mcp__bench__")]
    assert not off, f"non-bench tools allowed: {off}"


def test_no_tool_is_both_allowed_and_denied(argv):
    both = set(_flag(argv, "--allowedTools").split(",")) & \
           set(_flag(argv, "--disallowedTools").split(","))
    assert not both, f"contradictory: {both}"


# ---------------------------------------------------------------- the environment

def test_the_subscription_env_is_path_and_home_only():
    """Anything else here is a host secret handed to the agent's parent process."""
    assert set(cc._clean_env()) == {"PATH", "HOME"}


def test_the_api_env_adds_the_key_and_nothing_else():
    env = cc._clean_env(auth="api", api_key="sk-test", home="/tmp/isolated")
    assert set(env) == {"PATH", "HOME", "ANTHROPIC_API_KEY"}
    assert env["HOME"] == "/tmp/isolated", "an isolated HOME keeps OAuth out of the way"


def test_api_auth_without_a_key_is_refused():
    with pytest.raises(SystemExit):
        cc._clean_env(auth="api", api_key=None)


def test_the_argv_carries_no_host_path(argv):
    """The cwd is the staged workspace; the repo path must not leak through argv."""
    import pathlib
    repo = str(pathlib.Path(cc.__file__).resolve().parents[2])
    assert not [a for a in argv if repo in a]
