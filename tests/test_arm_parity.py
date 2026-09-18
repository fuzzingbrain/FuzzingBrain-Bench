"""claudecode and the external arm must be the same bench with a different agent.

v1 they were not: one drove the mcp-server inside the image, the other got a
staged host copy, a ./submit script and a ./reach responder. Every assertion
here is a difference that actually existed and was removed, so the test is a
ratchet -- it fails if any of them comes back.
"""
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


def test_both_arms_are_handed_the_same_task_text():
    assert ex.DEFAULT_OPENING == cc.claude_task_prompt()


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
