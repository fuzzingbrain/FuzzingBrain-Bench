# SPDX-License-Identifier: Apache-2.0
"""The external arm must report as it goes, like every other arm.

Before this, an fbagent cell wrote nothing until the agent process exited: a
30-minute run was unobservable and a killed one lost every graded candidate.
"""

import json
import tempfile
from pathlib import Path

from fbbench.sweep.external import Judge


def _judge(cell, preserve=True):
    ws = Path(tempfile.mkdtemp())
    j = Judge(ws, Path("/nonexistent"), cell_dir=cell, preserve_pocs=preserve)
    j._open_progress()
    j.blobs.mkdir(parents=True, exist_ok=True)
    return j


def _grade(j, name, crashed, sig, detail, size=64):
    (j.blobs / name).write_bytes(b"X" * size)
    e = {"blob": name, "size": size, "crashed": crashed, "signature": sig}
    j.log.append(e)
    j._record(e, j.blobs / name, detail)
    return e


# The live-grading bridge and the gdb/trace responder used to be tested here.
# Both were removed in fb-bench-v2: an agent now calls run_poc_on_harness on
# the same mcp-server every arm uses, and runs gdb itself inside the container,
# so there is no bench-side request bridge and no responder left to test.
#
# What went with them is an observability guarantee, not a fairness one:
# candidates used to be graded and copied out AS THEY ARRIVED, so a killed run
# still had them. Grading is post-hoc now (the same pass claudecode and codex
# use), so a killed run keeps its trace, usage and log but not its candidates.
# Restoring that means mirroring /workspace as the agent writes it -- worth
# doing, and deliberately not smuggled in with this change.


def test_the_manifest_receives_the_turn_budget():
    """An agent cannot honour a budget it is never told."""
    from fbbench.sweep.external import Manifest
    m = Manifest({"name": "x",
                  "command": "run --timeout {timeout} --max-turns {max_turns}"},
                 Path("."))
    argv = m.render(workspace="/w", timeout="1800", opening="o", submit="./submit",
                    max_turns="100")
    assert "--max-turns" in argv and "100" in argv
    assert not any("{max_turns}" in a for a in argv)


def test_turns_come_from_the_agent_report_not_the_trace():
    from fbbench.sweep.external import _agent_turns
    ws = Path("/nonexistent")
    assert _agent_turns({"turns": 70}, ws) == 70
    assert _agent_turns({"steps": 55}, ws) == 55      # older field name
    assert _agent_turns({"turns_used": 12}, ws) == 12


def test_no_report_falls_back_to_the_trace_count(tmp_path):
    from fbbench.sweep.external import _agent_turns
    (tmp_path / ".fbagent-trace.jsonl").write_text(
        '{"kind":"tool_call"}\n{"kind":"tool_result"}\n{"kind":"tool_call"}\n')
    assert _agent_turns(None, tmp_path) == 2
    assert _agent_turns({}, Path("/nonexistent")) == 0


# ---- wall-clock parity ------------------------------------------------------
# The external agent gets exactly the wall clock every other arm gets. The api
# episode self-stops at its deadline; claudecode hard-kills `claude -p` on the
# same one. This arm used to allow timeout_s+300 before the kill, which is real
# working time nobody else has.

def test_the_wall_clock_is_hard_and_takes_the_whole_process_group():
    import sys as _sys
    import time as _time
    from fbbench.sweep.external import _run_agent
    # The agent spawns a grandchild that outlives it and holds the pipe --
    # subprocess.run(timeout=...) kills only the direct child and would hang
    # here, letting the cell run past its budget.
    prog = ("import subprocess,sys,time;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)']);"
            "print('started',flush=True); time.sleep(120)")
    import tempfile
    log = Path(tempfile.mkdtemp()) / "agent.log"
    t0 = _time.time()
    out, timed_out = _run_agent([_sys.executable, "-c", prog], ".", None, 2, log)
    elapsed = _time.time() - t0
    assert timed_out
    assert elapsed < 5, elapsed
    # What the agent printed before the kill is still returned, not discarded.
    assert "started" in out


def test_an_agent_that_finishes_early_is_not_charged_the_clock():
    import sys as _sys
    import time as _time
    from fbbench.sweep.external import _run_agent
    import tempfile
    log = Path(tempfile.mkdtemp()) / "agent.log"
    t0 = _time.time()
    out, timed_out = _run_agent(
        [_sys.executable, "-c", "print('done')"], ".", None, 60, log)
    assert not timed_out
    assert "done" in out
    assert _time.time() - t0 < 10


def test_no_grace_period_is_added_to_the_agent_wall_clock():
    import inspect
    from fbbench.sweep import external
    src = inspect.getsource(external.run_cell)
    assert "timeout_s + " not in src, "the wall clock must never be extended"
    # It may only be CLAMPED DOWN, by the ceiling every agent arm shares.
    assert "min(timeout_s, AGENT_WALL_CAP_S)" in src


def test_the_manifest_is_told_which_model_to_run():
    # The bench prices the cell with its own `model`; an agent that never hears
    # it can run a different one, and the mismatch shows up as a cost, not as
    # a failure. Both spellings of the field are the same value.
    from fbbench.sweep.external import Manifest
    m = Manifest({"name": "x", "command": "run --model {model} --max-turns {max_turns}"}, Path("."))
    assert m.render(model="claude-opus-5", max_turns="100") == [
        "run", "--model", "claude-opus-5", "--max-turns", "100"]


# ---- evidence survives the run dying ----------------------------------------
# A bare-model cell flushes its dialogue every record, so whatever happens --
# the host goes down, the sweep is SIGKILLed, a connection drops -- there is a
# directory saying what was done and what it cost. An external cell used to hold
# its log in a pipe and its trace in a temp dir, both of which die with the
# process, in exactly the case where the money is already spent.

def test_the_agent_log_is_on_disk_while_the_agent_is_still_running(tmp_path):
    import subprocess as sp
    import sys
    import threading
    import time as t
    from fbbench.sweep.external import _run_agent

    log = tmp_path / "agent.log"
    prog = "import sys,time\nprint('turn 1', flush=True)\ntime.sleep(30)\n"
    seen = []

    def watch():
        for _ in range(100):
            if log.is_file() and "turn 1" in log.read_text():
                seen.append(True)
                return
            t.sleep(0.1)

    w = threading.Thread(target=watch)
    w.start()
    _run_agent([sys.executable, "-c", prog], str(tmp_path), None, 3, log)
    w.join()
    assert seen, "nothing was readable until the process exited"


def test_a_killed_agent_still_leaves_what_it_printed(tmp_path):
    import sys
    from fbbench.sweep.external import _run_agent
    log = tmp_path / "agent.log"
    prog = "import time\nprint('spent $4.10', flush=True)\ntime.sleep(60)\n"
    text, timed_out = _run_agent([sys.executable, "-c", prog], str(tmp_path), None, 2, log)
    assert timed_out
    assert "spent $4.10" in text
    assert "spent $4.10" in log.read_text()


def test_the_judge_mirrors_the_agents_files_out_of_the_doomed_workspace(tmp_path):
    from fbbench.sweep.external import Judge
    ws, cell = tmp_path / "ws", tmp_path / "cell"
    (ws / ".fbbench").mkdir(parents=True)
    cell.mkdir()
    judge = Judge(ws, tmp_path / "bug", cell_dir=cell)

    (ws / ".fbagent-trace.jsonl").write_text('{"kind":"text","text":"hello"}\n')
    (ws / ".fbbench" / "usage.json").write_text('{"model":"m","input_tokens":7}')
    judge._mirror()
    assert '"hello"' in (cell / "trace.jsonl").read_text()
    assert '"input_tokens": 7' in (cell / "usage.json").read_text().replace('"input_tokens":7', '"input_tokens": 7')

    # A later turn appends; the mirror has to follow, not stop at the first copy.
    (ws / ".fbagent-trace.jsonl").write_text('{"kind":"text","text":"hello"}\n{"kind":"text","text":"later"}\n')
    judge._mirror()
    assert '"later"' in (cell / "trace.jsonl").read_text()


def test_a_report_can_be_rendered_from_a_cell_that_never_finished(tmp_path):
    # The api arm flushes transcript.jsonl every record, so a killed cell still
    # renders its dialogue. This arm built the transcript at exit, so the one
    # run worth looking at -- the expensive one that died -- rendered empty.
    from fbbench.runner.report import build_report_html
    from fbbench.sweep.external import Judge

    ws, cell = tmp_path / "ws", tmp_path / "cell"
    (ws / ".fbbench").mkdir(parents=True)
    cell.mkdir()
    judge = Judge(ws, tmp_path / "bug", cell_dir=cell,
                  header={"bug_id": "avro-03", "model": "claude-opus-5", "max_turns": 100})
    (ws / ".fbagent-trace.jsonl").write_text(
        '{"step":1,"kind":"text","text":"Reading the harness."}\n'
        '{"step":1,"kind":"tool_call","tool":"bash","input":{"command":"./submit c1"}}\n'
        '{"step":1,"kind":"tool_result","tool":"bash","content":"crash: abrt|parse|main"}\n')
    judge._mirror()
    judge._record({"blob": "b1", "size": 8, "crashed": True, "signature": "abrt|parse|main"},
                  tmp_path / "missing", "crash: abrt|parse|main")

    html = build_report_html(cell)
    assert "avro-03" in html and "claude-opus-5" in html
    assert "Reading the harness." in html
    assert "./submit c1" in html
    assert "abrt|parse|main" in html
    assert "run did not finish" in html


def test_an_unfinished_run_reports_what_it_spent(tmp_path):
    # Tokens without dollars is not a cost report: it asks the reader to price
    # the run themselves, and an empty field reads as zero to anyone skimming.
    # A run that died is exactly when the number matters -- the money is gone
    # and the only open question is how much.
    from fbbench.runner.report import build_report_html
    from fbbench.sweep.external import Judge

    ws, cell = tmp_path / "ws", tmp_path / "cell"
    (ws / ".fbbench").mkdir(parents=True)
    cell.mkdir()
    judge = Judge(ws, tmp_path / "bug", cell_dir=cell,
                  header={"bug_id": "avro-03", "model": "claude-opus-5", "max_turns": 100})
    (ws / ".fbbench" / "usage.json").write_text(json.dumps({
        "model": "claude-opus-5", "input_tokens": 35217, "output_tokens": 6376,
        "cache_read_tokens": 537296, "cache_write_tokens": 29186,
        "input_is_total": False}))

    judge._record({"blob": "b1", "size": 8, "crashed": False, "signature": ""},
                  tmp_path / "missing", "clean: no fault")
    partial = json.loads((cell / "score.partial.json").read_text())

    # Priced by the bench's own table, through the one function that prices.
    from fbbench.sweep.external import price_reported_usage
    expected = price_reported_usage(json.loads((ws / ".fbbench" / "usage.json").read_text()),
                                    "claude-opus-5")["total_usd"]
    assert partial["total_usd"] == expected > 0
    assert partial["agent_reported"]["partial"] is True

    # And it has to reach the report, which reads cost off the top level.
    html = build_report_html(cell)
    assert f"{expected:.4f}" in html or f"{expected:.2f}" in html, expected
    assert "not reported" not in html


def test_the_live_price_and_the_final_price_come_from_one_function():
    # Two places computing money is how two numbers start disagreeing. That was
    # the reason not to price live; the answer is one function, not a blank field.
    import inspect
    from fbbench.sweep import external
    assert "price_reported_usage" in inspect.getsource(external._agent_usage)
    assert "price_reported_usage" in inspect.getsource(external.Judge._reported)
def test_the_agent_arms_get_the_api_arm_s_two_pieces_in_the_right_slots():
    """The api arm sends a SYSTEM prompt and, separately, a first USER turn
    built from setup(). An agent arm used to receive the system prompt AS its
    user message and never see the user turn at all -- so it never got the
    per-bug context block, the only place the sanitizer and its fault family
    appear. Both pieces now travel, each in its own slot."""
    from fbbench.prompts import build_initial_user_message, system_prompt
    from fbbench.sweep.external import DEFAULT_OPENING, agent_opening
    # the opening is the api arm's first user turn, not its system prompt
    assert DEFAULT_OPENING == build_initial_user_message({})
    assert DEFAULT_OPENING != system_prompt()
    # and it carries the context block once setup() has answered
    filled = agent_opening({"project": "libxml2", "language": "c",
                            "harness": {"sanitizer": "asan"}})
    assert "libxml2" in filled
    assert "./submit" not in filled        # a tool no arm has


def test_the_system_prompt_still_carries_the_methodology():
    """The instructions that used to be asserted on the opening live in the
    system prompt, which is where the api arm puts them."""
    from fbbench.prompts import system_prompt
    sp = system_prompt()
    assert "until one crashes" not in sp
    assert "Find ALL distinct vulnerabilities" in sp
    assert "Maximize the total count" in sp
    assert "run_poc_on_harness() is your only ground-truth" in sp
    assert "Do not build a harness" in sp


def test_both_agent_arms_are_handed_that_system_prompt():
    """Not folded into the user turn: the external arm gets it in the
    environment, claudecode on the command line."""
    import inspect
    from fbbench.sweep import claudecode as cc, external as ex
    assert "FBBENCH_SYSTEM_PROMPT" in inspect.getsource(ex)
    assert "--append-system-prompt" in inspect.getsource(cc)
