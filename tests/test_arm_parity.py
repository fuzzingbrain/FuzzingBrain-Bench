"""claudecode and the external arm must be the same bench with a different agent.

v1 they were not: one drove the mcp-server inside the image, the other got a
staged host copy, a ./submit script and a ./reach responder. Every assertion
here is a difference that actually existed and was removed, so the test is a
ratchet -- it fails if any of them comes back.
"""
import pytest
import subprocess
import json
import ast
import inspect
import textwrap

from fbbench.sweep import claudecode as cc
from fbbench.sweep import external as ex
from fbbench.sweep import mcp_episode


def _calls(fn, name):
    """Every call to `name` inside fn's source."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", None)) == name]


def test_both_arms_start_the_same_server():
    """One implementation, not two that agree. A second `docker run` for the
    external arm is how the cwd, the read-only /challenge and the per-command
    isolation drifted apart in the first place."""
    assert _calls(cc.stage_claude_env, "_start_episode_server"), "claudecode"
    assert _calls(ex.run_cell, "_start_episode_server"), "external"
    assert cc._start_episode_server is mcp_episode._start_episode_server
    assert ex._start_episode_server is mcp_episode._start_episode_server


def test_neither_arm_builds_its_own_container():
    """The external arm used to `docker run` a sleeping container and
    `docker exec` into it per command."""
    for fn in (ex.run_cell, cc.stage_claude_env):
        src = inspect.getsource(fn)
        assert "docker exec" not in src
        assert '"docker", "run"' not in src


def test_every_arm_is_handed_the_api_arm_s_task_text():
    """One brief. The api arm is the baseline every agent is measured against,
    so its prompt is the one that wins -- not CODEX_TASK_PROMPT, a second brief
    written for the codex arm whose goal sentence and crash definition differed
    from the baseline's by 64 lines."""
    from fbbench.prompts import system_prompt
    api = system_prompt()
    # An external agent calls the tools by their bare names, as the api arm
    # does, so it gets the text verbatim.
    assert ex.DEFAULT_OPENING == api
    # Claude Code namespaces MCP tools, so it gets exactly one substitution --
    # mechanical, forced by the client, and nothing else may differ.
    claude = cc.claude_task_prompt()
    assert claude != api
    undone = claude.replace("mcp__bench__", "")
    assert undone == api, "claudecode's prompt differs by more than the tool prefix"


def test_both_arms_observe_candidates_with_the_same_observer():
    """Live PoC preservation, from one place. claudecode used to have none at
    all; the external arm had its own request-directory watcher."""
    assert cc.CandidateLog is mcp_episode.CandidateLog
    assert ex.CandidateLog is mcp_episode.CandidateLog
    assert _calls(cc.stage_claude_env, "CandidateLog"), "claudecode builds one"
    assert _calls(ex.run_cell, "CandidateLog"), "external builds one"


def test_both_arms_grade_through_the_same_helper():
    """Three arms cannot report numbers that diverge for a reason nobody sees."""
    assert cc._crash_signatures is ex._crash_signatures
    assert _calls(cc._persist, "_crash_signatures")
    assert _calls(ex.run_cell, "_crash_signatures")


def test_the_external_arm_offers_no_tool_the_others_lack():
    """./submit and ./reach were bench-side tools only one arm had."""
    src = inspect.getsource(ex)
    for gone in ("def stage(", "class ContainerShell", "def make_sandbox",
                 "_gdb_script", "_run_gdb", "_serve_trace"):
        assert gone not in src, f"{gone} is back"
    assert "./submit" not in ex.DEFAULT_OPENING
    assert "./reach" not in ex.DEFAULT_OPENING


def test_every_agent_arm_shares_one_budget_ceiling():
    """A new rule, and it applies to agents only.

    The api arm drives its own loop and the bench counts its tokens between
    turns, so it keeps no dollar cap. Claude Code, codex and any external agent
    are black boxes that can run away, so each gets the same hard ceiling on
    both axes -- from one constant, not two that happen to match.
    """
    from fbbench.sweep import mcp_episode as ep

    assert ep.AGENT_WALL_CAP_S == 3600          # 1 hour per challenge
    assert ep.AGENT_USD_CAP == 10.0             # $10 per challenge
    for arm in (ex, cc):
        assert arm.AGENT_WALL_CAP_S is ep.AGENT_WALL_CAP_S
        assert arm.AGENT_USD_CAP is ep.AGENT_USD_CAP

    # and each arm must actually clamp with it, not merely import it
    assert "AGENT_WALL_CAP_S" in inspect.getsource(ex.run_cell)
    assert "AGENT_USD_CAP" in inspect.getsource(ex._run_agent)
    assert "AGENT_WALL_CAP_S" in inspect.getsource(cc.run_claude)
    assert "AGENT_USD_CAP" in inspect.getsource(cc.run_claude)


def test_the_api_arm_is_not_given_a_dollar_cap():
    """The rule is for agents. Capping the bare model would change what the
    agent arms are being compared against."""
    from fbbench.runner import episode
    assert "AGENT_USD_CAP" not in inspect.getsource(episode)


def test_no_arm_is_told_a_search_strategy_the_others_are_not():
    """claudecode used to get 695 characters of HARD RULES appended to its
    prompt -- "grade within your first 10 turns", "at least once every ~6" --
    and no other arm did. Nobody could say where 10 and 6 came from. An arm
    should be told what it cannot count for itself (turns, time) and nothing
    about what to do with it."""
    import inspect
    from fbbench.prompts import system_prompt

    # What reaches a model is what matters -- the source may still explain in a
    # comment why this was removed, and that is not a prompt.
    for text in (system_prompt(), ex.DEFAULT_OPENING, cc.claude_task_prompt()):
        assert "HARD RULES" not in text
        assert "MUST write a candidate" not in text

    # ...and neither arm may reach for the generators that produced them.
    for arm in (ex, cc):
        assert not hasattr(arm, "_budget_text"), arm.__name__
        assert not hasattr(arm, "_codex_nudge"), arm.__name__


def test_the_budget_line_is_the_api_arm_s_own_function():
    """One implementation of 'where the budget stands', not three that agree."""
    import inspect
    from fbbench import prompts
    assert "budget_note" in inspect.getsource(cc.run_claude)
    line = prompts.budget_note(30, 100, 70, elapsed_s=600.0,
                               remaining_s=1200.0, time_budget_s=1800.0)
    assert "turn 30/100" in line and "70 turns left" in line
    # facts only: no instruction about what to do with them
    for word in ("must", "now", "Write your best"):
        assert word not in line


def test_there_is_exactly_one_container_for_the_agent_arms():
    """Verified live on libavif-01 through the shared relay:

        TOOLS      ['exec', 'run_poc_on_harness', 'setup']
        cwd        /challenge
        identity   root
        writable   /challenge=ro  /workspace=rw  /tmp=rw
        gdb        /usr/bin/gdb, ptrace works
        network    DOWN
        graded bin /opt/fbbench/oracle/binaries/vuln/asan/harness  -rwx---r-x

    Both arms get that because there is ONE `docker run` between them, in the
    module they share. A second invocation in either arm is how the cwd, the
    read-only /challenge and the isolation drifted apart in v1.
    """
    import pathlib
    from fbbench.sweep import mcp_episode as ep

    assert '"docker", "run"' in inspect.getsource(ep._start_episode_server)
    for arm in (ex, cc):
        src = inspect.getsource(arm)
        assert '"docker"' not in src, f"{arm.__name__} starts its own container"

    # ...and both reach it through the same object, with the same argument shape.
    for fn in (ex.run_cell, cc.stage_claude_env):
        calls = _calls(fn, "_start_episode_server")
        assert len(calls) == 1, fn.__name__
        # (image, workspace, root, candidates) -- the observer is not optional
        assert len(calls[0].args) == 4, f"{fn.__name__} passes {len(calls[0].args)} args"


# ------------------------------------------------------------ the tool set
def test_claudecode_is_allowed_exactly_the_tools_that_exist():
    """The allowlist is the shared list, not a copy of it.

    A copy drifts, and a claudecode allowlist naming tools the other arms do
    not have reads as an advantage whether or not it is one.
    """
    from fbbench.sweep import claudecode as cc
    allowed = {t.removeprefix("mcp__bench__") for t in cc._BENCH_TOOLS.split(",")}
    assert allowed == set(mcp_episode.BENCH_TOOL_NAMES)


def test_the_api_arm_does_not_filter_tools_so_every_arm_sees_the_same_set():
    """The api arm takes whatever the in-image server advertises. If it ever
    started filtering, the agent arms would be compared against a baseline
    holding a different set of tools."""
    from fbbench.runner import mcp_client
    src = inspect.getsource(mcp_client.MCPClient.list_tools)
    assert "tools/list" in src
    assert "filter" not in src and "allowed" not in src


@pytest.mark.skipif(
    subprocess.run(["docker", "image", "inspect",
                    "osanzas/fbbench-challenge-libxml2-04:latest"],
                   capture_output=True).returncode != 0,
    reason="challenge image not present on this machine")
def test_the_shared_tool_list_matches_what_a_live_server_advertises():
    """Ground truth, asked of the server itself rather than assumed.

    BENCH_TOOL_NAMES is what claudecode's allowlist is built from and what the
    parity claim rests on. If a future challenge image ships a different
    mcp-server, this fails here rather than silently handing one arm a tool
    the others never hear about.
    """
    p = subprocess.Popen(
        ["docker", "run", "-i", "--rm", "--entrypoint", "mcp-server",
         "osanzas/fbbench-challenge-libxml2-04:latest"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True)
    try:
        def send(o):
            p.stdin.write(json.dumps(o) + "\n")
            p.stdin.flush()
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "parity-test", "version": "1"}}})
        p.stdout.readline()
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        names = None
        for _ in range(6):
            line = p.stdout.readline()
            if not line:
                break
            m = json.loads(line)
            if m.get("id") == 2:
                names = {t["name"] for t in m["result"]["tools"]}
                break
    finally:
        p.kill()
    assert names == set(mcp_episode.BENCH_TOOL_NAMES), (
        f"the image advertises {names}, the bench believes "
        f"{set(mcp_episode.BENCH_TOOL_NAMES)}")
