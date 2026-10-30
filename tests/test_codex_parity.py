"""The codex arm is the Claude Code arm with a different CLI.

It used to be its own bench: the published challenge image (no gdb, no call
graph), a second brief (CODEX_TASK_PROMPT) with TIME BUDGET coaching appended,
a turn budget with no dollar cap, ExploitBench nudges, the final workspace as
the only record of what was graded, and no 401 detection. Every assertion here
is one of those differences, and fails if it comes back.
"""
import ast
import inspect
import textwrap

import pytest

from fbbench.sweep import claudecode as cc
from fbbench.sweep import codex as cx
from fbbench.sweep import mcp_episode as ep


def _calls(fn, name):
    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    return [n for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and getattr(n.func, "id", getattr(n.func, "attr", None)) == name]


def test_codex_is_handed_claude_codes_text():
    env = {"gdb": True, "callgraph": True}
    setup = {"project": "p", "language": "c"}
    assert cx.codex_task_prompt(setup, env) == cc.claude_task_prompt(setup, env)
    assert cx.codex_task_prompt() == cc.claude_task_prompt()
    for text in (cx.codex_task_prompt(), cx.codex_task_prompt(setup, env)):
        assert "TIME BUDGET" not in text
        assert "RESULT.md" not in text
    assert "CODEX_TASK_PROMPT" not in inspect.getsource(cx)
    assert not hasattr(cx, "_codex_nudge")


def test_codex_gets_the_api_arm_system_prompt_as_developer_instructions(tmp_path):
    tomllib = pytest.importorskip("tomllib")
    from fbbench.sweep.external import agent_system_prompt
    env = {"gdb": True, "callgraph": True}
    text = cx.codex_config(model="gpt-5.5", login="api",
                           instructions=agent_system_prompt(env),
                           relay_path="/r", sock_path="/s")
    cfg = tomllib.loads(text)
    assert cfg["developer_instructions"] == agent_system_prompt(env)
    assert "top three stack frames" in cfg["developer_instructions"]
    src = "".join(inspect.getsource(cx.stage_codex_env).split())
    assert "instructions=agent_system_prompt(env_caps)" in src


def test_codex_has_no_tool_of_its_own():
    tomllib = pytest.importorskip("tomllib")
    cfg = tomllib.loads(cx.codex_config(model="m", login="api", instructions="",
                                        relay_path="/r", sock_path="/s"))
    assert cfg["web_search"] == "disabled"
    for f in ("shell_tool", "unified_exec", "browser_use", "computer_use",
              "apps", "multi_agent", "image_generation", "view_image"):
        assert cfg["features"][f] is False, f
    # the only server is the bench, named as Claude Code names it
    assert list(cfg["mcp_servers"]) == ["bench"]


def test_codex_runs_in_the_agent_image_through_the_shared_server():
    src = inspect.getsource(cx.stage_codex_env)
    assert "agent_image(alias)" in src
    calls = _calls(cx.stage_codex_env, "_start_episode_server")
    assert len(calls) == 1 and len(calls[0].args) == 4
    assert cx._start_episode_server is ep._start_episode_server
    assert cx.CandidateLog is ep.CandidateLog
    for helper in ("CandidateLog", "fetch_setup", "probe_environment",
                   "install_gdb_source_map"):
        assert _calls(cx.stage_codex_env, helper), helper
    assert '"docker"' not in inspect.getsource(cx)


def test_the_matrix_pulls_the_agent_image_for_codex():
    from fbbench.sweep import orchestrator
    from fbbench.images import agent_image
    from fbbench.runner.mcp_client import _full_scan_alias
    from fbbench.grading import find_bug
    bug = orchestrator.discover_bugs()[0]
    alias = _full_scan_alias(str(find_bug(bug)))
    assert orchestrator._run_images("codex", [bug], None) == [agent_image(alias)]


def test_codex_runs_under_the_same_ceilings_and_budget_line():
    assert cx.AGENT_WALL_CAP_S is ep.AGENT_WALL_CAP_S
    assert cx.AGENT_USD_CAP is ep.AGENT_USD_CAP
    src = inspect.getsource(cx.run_codex)
    for name in ("AGENT_WALL_CAP_S", "AGENT_USD_CAP", "budget_note"):
        assert name in src, name
    assert cx.MAX_RESUMES == cc.MAX_RESUMES


def test_codex_records_what_claude_code_records():
    def keys(fn):
        for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(fn)))):
            if (isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "score"
                    and isinstance(n.value, ast.Dict)):
                return {k.value for k in n.value.keys}
    missing = keys(cc._persist) - keys(cx._persist)
    assert not missing, missing


def _fake(monkeypatch, stats, runs):
    calls = {"n": 0}

    def once(argv, env, lf, deadline, codex_home, model, max_turns, usd_cap):
        calls["n"] += 1
        calls.setdefault("argv", []).append(argv)
        return runs.pop(0) if runs else {"ended": "exited", "session_id": "s1", "error": None}
    monkeypatch.setattr(cx, "_run_codex_once", once)
    monkeypatch.setattr(cx, "_rollout_stats", lambda *a, **k: dict(stats))
    return calls


_BASE = {"turns": 3, "grade_calls": 1, "last_grade_turn": 2, "tokens": 10,
         "input_tokens": 8, "output_tokens": 2, "cache_read_tokens": 0,
         "cache_write_tokens": 0, "usd": 0.5,
         "session_id": "s1", "said_complete": False, "models": ["gpt-5.5"],
         "refused": False, "graded_paths": [], "other_calls": []}


def test_codex_ends_when_the_agent_says_it_is_done(monkeypatch, tmp_path):
    calls = _fake(monkeypatch, {**_BASE, "said_complete": True}, [])
    r = cx.run_codex(str(tmp_path), str(tmp_path), str(tmp_path), "gpt-5.5", 60, 10000)
    assert r["terminated"] == "done" and calls["n"] == 1


def test_codex_resumes_its_session_with_the_shared_budget_line(monkeypatch, tmp_path):
    calls = _fake(monkeypatch, _BASE, [{"ended": "exited", "session_id": "s1", "error": None},
                                       {"ended": "cost-cap", "session_id": "s1", "error": None}])
    r = cx.run_codex(str(tmp_path), str(tmp_path), str(tmp_path), "gpt-5.5", 60, 10000)
    assert r["terminated"] == "cost-cap"
    resume = calls["argv"][1]
    assert resume[:3] == ["codex", "exec", "resume"] and "s1" in resume
    assert resume[-1].startswith("[Budget: turn 3/10000")


def test_a_401_ends_the_cell_instead_of_a_false_zero(monkeypatch, tmp_path):
    calls = _fake(monkeypatch, {**_BASE, "turns": 0},
                  [{"ended": "auth_error", "session_id": None, "error": "401 Unauthorized"}])
    r = cx.run_codex(str(tmp_path), str(tmp_path), str(tmp_path), "gpt-5.5", 60, 10000)
    assert r["terminated"] == "auth_error" and calls["n"] == 1
    assert r["api_error"] == "401 Unauthorized"


def test_another_model_is_never_scored_as_the_one_asked_for(monkeypatch, tmp_path):
    _fake(monkeypatch, {**_BASE, "models": ["gpt-5.5", "gpt-5.4"]},
          [{"ended": "refusal", "session_id": "s1", "error": None}])
    r = cx.run_codex(str(tmp_path), str(tmp_path), str(tmp_path), "gpt-5.5", 60, 10000)
    assert r["terminated"] == "refusal"
    assert r["model_fallback"]["to"] == "gpt-5.4"
    assert cx._other_models(["gpt-5.5-2026-09-01"], "gpt-5.5") == []
