"""claudecode and the external arm must be the same bench with a different agent.

v1 they were not: one drove the mcp-server inside the image, the other got a
staged host copy, a ./submit script and a ./reach responder. Every assertion
here is a difference that actually existed and was removed, so the test is a
ratchet -- it fails if any of them comes back.
"""
import pytest
import subprocess
import json
import re
import os
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
    from fbbench.prompts import build_initial_user_message, system_prompt
    api = build_initial_user_message({})
    # Both arms are handed the api arm's FIRST USER TURN, not its system
    # prompt: that travels separately, in the system slot.
    assert ex.DEFAULT_OPENING == api
    # Claude Code namespaces MCP tools, so it gets exactly one substitution --
    # mechanical, forced by the client, and nothing else may differ.
    claude = cc.claude_task_prompt()
    assert claude != api
    undone = claude.replace("mcp__bench__", "")
    # Both agent arms also carry the toolbox line, which the api arm does not:
    # it runs in the published images and has neither gdb nor a readable
    # target. That line is identical for both agent arms, and it is the ONLY
    # thing either of them has beyond the baseline text.
    assert undone == api + mcp_episode.agent_tools_note(), \
        "claudecode's prompt differs by more than the tool prefix and the toolbox line"


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


# ------------------------------------------------- knowing the tools exist
def test_both_agent_arms_are_told_about_the_environment_in_the_same_words():
    """One sentence, in the system prompt, identical for both arms -- and the
    only difference between what an agent is told and what the baseline is told.

    An asymmetry in information is the same unfairness as one in tools: one arm
    knowing it has a debugger while the other has to guess is not a comparison.
    """
    caps = {"gdb": True, "target": mcp_episode.ORACLE_HARNESS}
    note = mcp_episode.agent_tools_note(caps)
    assert note and "\n" not in note, "one line, not a section"
    assert note.startswith("- "), "a bullet, so it reads as one of the steps"
    # the system prompt is the api arm's, verbatim, plus exactly that one line
    from fbbench.prompts import build_initial_user_message, system_prompt
    api = system_prompt()
    sp_full = ex.agent_system_prompt(caps)
    assert [l for l in sp_full.splitlines() if l not in api.splitlines() or
            api.splitlines().count(l) < sp_full.splitlines().count(l)] == [note]
    # it sits under the bullet about the graded binary, not after the whole prompt
    body = sp_full.splitlines()
    assert body[body.index(note) - 1].startswith(mcp_episode._TOOLS_ANCHOR)
    assert not sp_full.rstrip().endswith(note), "stranded at the end"
    assert sp_full.splitlines()[-1] == api.splitlines()[-1], "closing line moved"
    # and the user turn is the api arm's, untouched
    assert ex.agent_opening() == build_initial_user_message({})
    # claudecode passes the same string, differing only by the forced prefix
    sp = ex.agent_system_prompt(caps)
    assert "--append-system-prompt" in inspect.getsource(cc)
    assert "agent_system_prompt" in inspect.getsource(cc)
    undone = cc.claude_task_prompt(None, caps).replace("mcp__bench__", "")
    assert undone == build_initial_user_message({})


def test_the_toolbox_line_never_reaches_the_api_arm():
    """prompts.system_prompt() is the baseline every agent is measured
    against. Changing it makes v1 api results incomparable, and the api arm
    has no toolbox to be told about."""
    from fbbench import prompts
    for word in ("gdb", "Also available in this environment"):
        assert word not in prompts.system_prompt()
        assert word not in prompts.build_initial_user_message({})


def test_the_note_cannot_promise_a_tool_that_is_not_mounted():
    """Generated from what is actually mounted. With the toolbox off both
    agent arms fall back to the api arm's text exactly."""
    from fbbench import prompts
    assert ex.agent_opening() == prompts.build_initial_user_message({})


def test_the_opening_is_built_per_cell_not_at_import():
    """Resolving the toolbox can pull an image; importing a module must not."""
    src = inspect.getsource(ex)
    assert "DEFAULT_OPENING = default_opening()" in src
    assert "agent_tools_note()" not in src.split("def agent_opening")[0]


def test_the_note_names_the_target_only_when_it_is_readable():
    """A prompt that promises a path the kernel refuses costs turns: a live run
    spent 2 of its 12 on exactly that. The line is built from a probe of the
    running container, so it can only name what is actually there."""
    caps = {"gdb": True, "target": mcp_episode.ORACLE_HARNESS}
    assert mcp_episode.ORACLE_HARNESS in mcp_episode.agent_tools_note(caps)
    assert mcp_episode.ORACLE_HARNESS not in mcp_episode.agent_tools_note({"gdb": True})
    assert mcp_episode.agent_tools_note({}) == ""
    assert "gdb" not in mcp_episode.agent_tools_note({"target": mcp_episode.ORACLE_HARNESS})


def test_claude_code_cost_is_not_summed_across_resumes():
    """total_cost_usd is the SESSION's running total, not one turn's cost.

    A resume continues the same session and re-reports the whole figure, so
    adding them compounds. On libavif-01 twelve resumes reported 0.825, 0.841,
    0.856 ... 0.993 -- one $0.99 run recorded as $10.87. The phantom total then
    tripped the $10 agent cap and killed the run at turn 85 of 100 for money it
    had never spent, and the same happened on systemd-01 at turn 75.
    """
    src = inspect.getsource(cc)
    assert 'st["usd"] +=' not in src, "cost must never be accumulated with +="
    assert "cost_by_session" in src
    assert "usd = sum(cost_by_session.values())" in src


def test_resumes_of_one_session_cost_what_the_session_says():
    """The arithmetic itself, on the numbers that produced the bug."""
    reported = [0.8252, 0.8411, 0.8562, 0.8711, 0.8854, 0.8989,
                0.9121, 0.9254, 0.9389, 0.9524, 0.9658, 0.9932]
    by_session: dict = {}
    for v in reported:
        by_session["session-A"] = v          # a resume overwrites its session
    assert round(sum(by_session.values()), 4) == 0.9932
    assert round(sum(reported), 4) == 10.8657   # what the old code recorded
    by_session["session-B"] = 1.19              # a genuinely new session adds
    assert round(sum(by_session.values()), 4) == 2.1832


def test_the_agent_image_set_is_for_agent_arms_only():
    """The asymmetry is which IMAGE each arm runs in, not what gets mounted.

    Both agent arms resolve fbbench-agent/<alias>, which ships gdb and leaves
    the vulnerable build readable. The api arm resolves the published
    challenge image, unchanged, because its v1 numbers were produced there and
    they are the baseline every agent is measured against.
    """
    from fbbench.runner import mcp_client
    from fbbench import images
    assert "agent_image" in inspect.getsource(ex)
    assert "agent_image" in inspect.getsource(cc)
    assert "agent_image" not in inspect.getsource(mcp_client)
    assert images.agent_image("x-01") != images.challenge_image("x-01")
    assert images.challenge_image("x-01").startswith("docker.io/osanzas/fbbench-challenge-")


def test_the_episode_server_mounts_nothing_but_the_workspace():
    """The bind-mount workaround is gone with the images that needed it: no
    toolbox image, no extracted copy of the target, no host cache."""
    src = inspect.getsource(mcp_episode._start_episode_server)
    for gone in ("agent_tool_mounts", "target_harness_mount", "AGENT_TOOLS_IMAGE"):
        assert gone not in src


def test_the_probe_asks_the_container_rather_than_assuming():
    src = inspect.getsource(mcp_episode.probe_environment)
    assert "command -v gdb" in src and "test -r" in src
    for arm in (ex, cc):
        assert "probe_environment" in inspect.getsource(arm)


def test_a_published_image_is_always_refetched_and_a_local_one_is_not():
    """A stale cached :latest must never grade a run, and an image that lives
    only on this machine has nowhere to be fetched from -- --pull=always would
    fail the cell before it started. Both published sets are registry
    references and are always re-fetched."""
    from fbbench import images
    assert images.pull_policy(images.challenge_image("x-01")) == "always"
    assert images.pull_policy(images.agent_image("x-01")) == "always"
    assert images.pull_policy("fbbench-agent/x-01:latest") == "missing"
    assert "pull_policy" in inspect.getsource(mcp_episode._start_episode_server)


def test_the_resume_loop_runs_with_no_undefined_names():
    """run_claude() has now lost code twice to careless edits, and nothing
    exercised it: the cost accumulator was summed instead of keyed, and later
    its five initialisation lines were deleted with a comment block. Both
    reached a real run before anything noticed. This drives the loop with a
    stubbed subprocess so the function is at least executed."""
    import types
    from fbbench.sweep import claudecode as c
    calls = {"n": 0}

    def fake_once(argv, lf, deadline, work="", snap_dir="", env=None):
        calls["n"] += 1
        return {"turns": 100, "grade_calls": 1, "tokens": 10, "input_tokens": 1,
                "output_tokens": 1, "cache_read_tokens": 0, "cache_write_tokens": 0,
                "usd_by_session": {"s1": 0.5}, "session_id": "s1", "ended": "exited"}

    orig = c._run_claude_once
    c._run_claude_once = fake_once
    try:
        import tempfile, os
        work = tempfile.mkdtemp()
        r = c.run_claude(work, os.path.join(work, "mcp.json"), "claude-haiku-4-5",
                         timeout_s=60, max_turns=100, auth="api", api_key="x")
    finally:
        c._run_claude_once = orig
    assert calls["n"] >= 1
    assert r["terminated"] == "turn_budget"
    assert r["total_usd"] == 0.5, "a single session must not be summed twice"


def test_a_cell_records_the_prompt_the_agent_was_actually_sent():
    """It recorded prompts.system_prompt() while sending that plus the
    environment line, so the report showed 2504 chars with no mention of gdb
    while 3107 chars went over the wire. A transcript that does not match the
    request is worse than no transcript."""
    src = inspect.getsource(ex)
    assert '"system_prompt": system_prompt()' not in src
    assert "system_prompt_sent" in src
    assert "agent_system_prompt(env_caps)" in src


def test_the_claudecode_cell_records_what_it_sent_too():
    """The external arm recorded prompts.system_prompt() while sending more; this
    arm recorded the USER turn in the system slot and nothing in the user slot,
    so a full 100-turn run reported a 638-char system prompt with no mention of
    gdb and an empty first message."""
    src = inspect.getsource(cc)
    assert '"system_prompt": claude_task_prompt()' not in src
    assert '"system_prompt": system_prompt_sent' in src
    assert '"initial_user_message": user_turn_sent' in src
    assert '"system_prompt_sent": agent_system_prompt(env_caps)' in src


def test_both_arms_render_the_model_exchange_inside_each_turn(tmp_path):
    """The exchange belongs in the turn it produced, not in a separate section.

    fbagent records the full messages array it posted; the claudecode CLI never
    exposes one, so that arm writes the appended messages plus a running count.
    Both shapes have to reach the turn, and neither may repeat the prefix every
    call -- that is what made this page 36 MB.
    """
    from fbbench.runner.report import (_load_exchange, _exchange_by_turn,
                                       _conversation_html)

    assert _load_exchange(tmp_path) == []          # no log, nothing to attach

    full = {"model": "m", "request": {"messages": [
        {"role": "system", "content": "SYSPROMPT"},
        {"role": "user", "content": "OPENING"}]},
        "response": {"choices": [{"message": {"role": "assistant",
                                             "content": "FIRST REPLY"},
                                  "finish_reason": "stop"}],
                     "usage": {"prompt_tokens": 10, "completion_tokens": 2}}}
    grown = {"model": "m", "request": {"messages": full["request"]["messages"] + [
        {"role": "assistant", "content": "FIRST REPLY"},
        {"role": "user", "content": "SECOND TURN"}]},
        "response": {"choices": [{"message": {"role": "assistant",
                                              "content": "SECOND REPLY"}}]}}
    (tmp_path / "exchange.jsonl").write_text(
        json.dumps(full) + "\n" + json.dumps(grown) + "\n")
    wire = _exchange_by_turn(_load_exchange(tmp_path))
    assert sorted(wire) == [1, 2]

    turns = [{"turn": 1, "text": "a", "stop": "", "in_tok": 0, "out_tok": 0,
              "notes": [], "calls": []},
             {"turn": 2, "text": "b", "stop": "", "in_tok": 0, "out_tok": 0,
              "notes": [], "calls": []}]
    html = _conversation_html(turns, "S", "U", wire)
    for must in ("SYSPROMPT", "OPENING", "SECOND TURN", "FIRST REPLY",
                 "SECOND REPLY", "4 messages posted", "raw exchange"):
        assert must in html, must
    # one block per turn, and the prefix rendered once rather than per call
    assert html.count('class="wire"') == 2
    assert html.count("SYSPROMPT") == 1
    assert "2 messages from the turns above" in html

    delta = {"model": "m", "source": "reconstructed", "turn": 7,
             "request": {"message_count": 3,
                         "messages_appended": [{"role": "user", "content": "DELTA MSG"}]},
             "response": {"choices": [{"message": {"role": "assistant",
                                                   "content": "DELTA REPLY"}}]}}
    (tmp_path / "exchange.jsonl").write_text(json.dumps(delta) + "\n")
    wire = _exchange_by_turn(_load_exchange(tmp_path))
    assert sorted(wire) == [7]                     # keyed by its own turn number
    html = _conversation_html(
        [{"turn": 7, "text": "", "stop": "", "in_tok": 0, "out_tok": 0,
          "notes": [], "calls": []}], "S", "U", wire)
    assert "DELTA MSG" in html and "DELTA REPLY" in html
    assert "3 messages posted" in html
    assert "request rebuilt from the stream" in html   # labelled, not claimed


def test_a_thinking_block_does_not_dump_its_signature(tmp_path):
    """An empty thinking block carries a page of base64 and no meaning."""
    from fbbench.runner.report import _msg_text

    out = _msg_text([{"type": "thinking", "thinking": "", "signature": "A" * 400},
                     {"type": "text", "text": "the actual words"}])
    assert "A" * 40 not in out
    assert "the actual words" in out
    assert "[thinking block, empty]" in out


def test_one_response_is_one_turn(tmp_path):
    """Text and the tool call it arrived with are one response, not two turns."""
    from fbbench.runner.report import build_conversation

    t = tmp_path / "transcript.jsonl"
    t.write_text("\n".join(json.dumps(e) for e in [
        {"event": "start", "system_prompt": "S", "initial_user_message": "U"},
        {"event": "assistant", "turn": 1, "text": "thinking out loud",
         "stop_reason": None, "tool_calls": []},
        {"event": "assistant", "turn": 1, "text": "", "stop_reason": "tool_use",
         "tool_calls": [{"id": "a", "name": "exec", "input": {"cmd": "ls"}}]},
        {"event": "tool_result", "id": "a", "tool": "exec", "result": "ok"},
    ]) + "\n")
    turns, sp, iu = build_conversation(t)
    assert (sp, iu) == ("S", "U")
    assert len(turns) == 1
    assert turns[0]["text"] == "thinking out loud"
    assert [c["tool"] for c in turns[0]["calls"]] == ["exec"]
    assert turns[0]["stop"] == "tool_use"


def test_gdb_is_given_the_source_the_debug_info_points_at():
    """Mapping the build paths is what makes gdb able to show a line.

    The debug info names the machine that compiled the target -- /src/harness
    and /src/<project>-<san> -- and neither exists in the image, so every stop
    printed "No such file or directory". Only the first component under /src is
    a root: a path like .../lang/c/src/map.c contains "/src/" too, and treating
    that as one produced 27 rules where 2 were needed.
    """
    from fbbench.sweep.mcp_episode import (GDB_CONFIG_HOME, GDB_INIT_PATH,
                                           _source_roots, _start_episode_server)

    out = ("/src/harness/harness.c, /usr/lib/llvm-14/include/stddef.h, "
           "/src/avro-asan/lang/c/src/map.c, /src/avro-asan/lang/c/src/avro/io.h, "
           "/usr/include/stdio.h")
    assert _source_roots(out) == ["/src/harness", "/src/avro-asan"]
    assert _source_roots("") == []
    assert _source_roots("/usr/include/stdio.h") == []
    assert _source_roots("/src/x") == []            # no file under it, not a root

    # gdb must be pointed at the one writable path: the image root is read-only,
    # so $HOME/.gdbinit cannot be written -- only /workspace can.
    assert GDB_CONFIG_HOME.startswith("/workspace")
    assert GDB_INIT_PATH == GDB_CONFIG_HOME + "/gdb/gdbinit"
    src = inspect.getsource(_start_episode_server)
    assert "XDG_CONFIG_HOME" in src, "gdb would never read the file"


def test_both_arms_install_the_source_map():
    """Neither arm may be the only one whose gdb can show source."""
    for mod in (ex, cc):
        src = inspect.getsource(mod)
        assert "install_gdb_source_map" in src, mod.__name__


def test_a_failed_source_map_is_not_reported_as_a_working_one():
    """Writing the file proves nothing -- a gdb older than 11 never reads it.

    Silently returning the rules there would tell a reader gdb can show source
    when it cannot, which is the same failure as a prompt naming a path the
    kernel refuses. The install asks gdb what it loaded.
    """
    from fbbench.sweep import mcp_episode as me

    src = inspect.getsource(me.install_gdb_source_map)
    assert "show substitute-path" in src, "the install never verifies itself"
    assert src.index("show substitute-path") > src.index("FBEOF"), \
        "verification must come after the write"

    calls = []

    def fake_exec(sock, cmd, timeout=0.0):
        calls.append(cmd)
        if "info sources" in cmd:
            return "/src/harness/harness.c, /src/proj-asan/a.c"
        if cmd.startswith("test -d"):
            return "OK" if ("/challenge/harness" in cmd or "/challenge/src" in cmd) else ""
        if "show substitute-path" in cmd:
            return calls.pop() and ""      # gdb loaded nothing
        return ""

    orig = me._exec_once
    me._exec_once = fake_exec
    try:
        assert me.install_gdb_source_map("s") == [], "unverified rules reported"
        # and when gdb does confirm them, they come back
        # only the dirs that really exist in an image answer OK
        me._exec_once = lambda s, c, t=0.0: (
            "/src/harness/harness.c, /src/proj-asan/a.c" if "info sources" in c
            else ("OK" if ("/challenge/harness" in c or "/challenge/src" in c) else "")
            if c.startswith("test -d")
            else "rule: /src/harness -> x\nrule: /src/proj-asan -> y"
            if "show substitute-path" in c else "")
        assert me.install_gdb_source_map("s") == [
            "set substitute-path /src/harness /challenge/harness",
            "set substitute-path /src/proj-asan /challenge/src"]
    finally:
        me._exec_once = orig


def test_the_source_map_can_never_be_graded_as_a_candidate():
    """It lives in the workspace the agent also writes PoCs into."""
    from fbbench.sweep.mcp_episode import GDB_CONFIG_HOME
    import glob as _glob

    # hidden, so the one arm that scans the workspace cannot pick it up
    assert os.path.basename(GDB_CONFIG_HOME).startswith("."), \
        "a visible dir here would be swept up as a candidate blob"
    assert "*" not in _glob.escape(GDB_CONFIG_HOME)


def test_a_model_id_with_a_colon_makes_an_openable_path():
    """ollama ids carry a colon, and Firefox reads it as a protocol.

    The report then cannot be opened by double-click. Only the path is
    sanitised -- score.json keeps the id verbatim -- and the summary has to
    build the path the same way or it stops finding the cells.
    """
    from pathlib import Path
    from fbbench.sweep.orchestrator import cell_dir

    d = cell_dir(Path("out"), "avro-03", "fb-agent-qwen3.8:27b", 0)
    assert ":" not in str(d)
    assert d == Path("out/avro-03/fb-agent-qwen3.8-27b/seed-0")
    # unaffected for ordinary ids
    assert cell_dir(Path("out"), "avro-03", "claude-haiku-4-5", 0) == \
        Path("out/avro-03/claude-haiku-4-5/seed-0")

    src = inspect.getsource(__import__("fbbench.report.summary",
                                      fromlist=["x"]))
    assert "cell_dir(" in src, "the summary builds its own path and will miss cells"


def test_claudecode_may_end_on_its_own_judgement():
    """Both arms must be able to finish, not only be cut off.

    The system prompt grants the run an end -- say ASSESSMENT COMPLETE and stop
    calling tools. The CLI ends its turn sequence there and the arm used to
    resume regardless, so every claudecode cell on record ended at a cap while
    every fbagent cell ended on the agent's own call. That is not one budget
    applied to two arms.
    """
    src = inspect.getsource(cc)
    assert '"said_complete"' in src, "no completion signal is tracked"
    assert "ASSESSMENT COMPLETE" in src, "the prompt's own phrase is not looked for"
    # the claim has to be revocable: a tool call after it means work continued
    assert re.search(r'tool_use".*\n\s*st\["said_complete"\] = False', src), \
        "a tool call after the claim must clear it"
    # and it has to end the resume loop with the same reason fbagent reports
    loop = src[src.index("for attempt in range(MAX_RESUMES"):]
    assert 'st.get("said_complete")' in loop, "the resume loop ignores completion"
    i = loop.index('st.get("said_complete")')
    assert 'terminated = "done"' in loop[i:i + 220], "must report the agent's own end"

    # the resume cap must not be the budget either
    assert cc.MAX_RESUMES >= 200, (
        f"MAX_RESUMES={cc.MAX_RESUMES} caps a cell below its wall/cost budget")


def test_only_submitted_blobs_are_graded():
    """The prompt's rule: an input never run through the oracle does not count.

    Sweeping the workspace also graded inputs the agent never claimed, and with
    an hour of budget one agent left 5,581 files behind -- the end-of-run pass
    then held a worker for hours grading them one at a time.
    """
    src = inspect.getsource(cc)
    i = src.index("blobs = sorted(set(")
    block = src[i:i + 320]
    assert "candidates.host_blobs()" in block, "submitted blobs must be graded"
    assert "_graded_paths(" in block, "blobs recovered from the log must be graded"
    assert "_candidate_blobs(work)" not in block, \
        "the workspace sweep grades inputs the agent never submitted"


def test_a_bare_fatal_signal_is_not_reported_as_a_crash():
    """The live trail must judge a candidate the way the scorer judges it.

    A harness that dies during sanitizer start-up produces a signal and no
    output. The old label called that a crash: the same bytes then ran clean on
    a retry, the score correctly refused it, but the agent had been told it
    found something -- 30 such reports across 23 of 76 cells in one sweep, and
    one agent resubmitted the same phantom three times.
    """
    from fbbench.sweep.mcp_episode import _harness_output, _signature_of

    silent = {"harness_output": {"exit_code": -1, "signal": "SIGSEGV",
                                 "stderr": "", "stdout": ""}}
    ho = _harness_output(silent)
    assert ho is not None and _signature_of(ho) is None, \
        "a bare signal with no sanitizer output must name no fault"

    # a real fault the sanitizer named, with no frames, still counts
    oom = {"harness_output": {"exit_code": 71, "signal": "", "stderr":
           "==1==ERROR: libFuzzer: out-of-memory\nSUMMARY: libFuzzer: out-of-memory\n"}}
    assert _signature_of(_harness_output(oom)) == "out-of-memory|<no-frames>"

    # and the payload is found whatever shape the tool result arrives in
    inner = json.dumps({"harness_output": silent["harness_output"]})
    assert _harness_output({"content": [{"text": inner}]}) is not None
    assert _harness_output({"structuredContent": silent}) is not None
    assert _harness_output("not json") is None


def test_the_grader_does_not_pull_per_candidate():
    """A grading container starts per candidate; pulling each time throttled us.

    --pull=always there made one registry request per graded blob. A median cell
    grades 30, so a sweep asked Docker Hub over a thousand times and Hub began
    refusing with TLS timeouts, failing whole cells mid-run. The image is still
    fetched once per process, so a stale :latest cannot score a run.
    """
    from fbbench.runner import mcp_client as mc

    src = inspect.getsource(mc)
    assert "--pull=missing" in src, "grading still pulls on every container"
    assert "_pull_once(image)" in src, "the image is never fetched at all"

    seen = []
    real = mc.subprocess.run

    class _Ok:
        returncode = 0; stdout = ""; stderr = ""

    def fake(cmd, *a, **k):
        if isinstance(cmd, list) and cmd[:2] == ["docker", "pull"]:
            seen.append(cmd[-1]); return _Ok()
        return real(cmd, *a, **k)

    mc.subprocess.run = fake
    try:
        mc._PULLED.discard("img:latest")
        for _ in range(5):
            mc._pull_once("img:latest")
        assert len(seen) == 1, f"pulled {len(seen)} times, want 1"
    finally:
        mc.subprocess.run = real
        mc._PULLED.discard("img:latest")
