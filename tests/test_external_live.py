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


def test_every_candidate_is_readable_before_the_run_ends(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell)
    _grade(j, "b0", False, "", "clean: no fault | target ran 0 ms | 64 bytes")
    _grade(j, "b1", True, "abrt|f|g", "crash: abrt|f|g")
    recs = [json.loads(l) for l in (cell / "progress.jsonl").read_text().splitlines()]
    assert len(recs) == 2
    assert recs[0]["crashed"] is False and "0 ms" in recs[0]["verdict"]
    assert recs[1]["crashed"] is True and recs[1]["unique_so_far"] == 1


def test_pocs_are_preserved_as_they_are_graded(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell)
    _grade(j, "b0", False, "", "clean: no fault | target ran 0 ms | 64 bytes")
    _grade(j, "b1", True, "abrt|f|g", "crash: abrt|f|g")
    assert (cell / "pocs" / "clean" / "b0").is_file()
    assert (cell / "pocs" / "crashed" / "b1").is_file()
    meta = json.loads((cell / "pocs" / "crashed" / "b1.json").read_text())
    assert meta["crash_signature"] == "abrt|f|g" and meta["crashed"] is True


def test_a_running_tally_is_written(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell)
    _grade(j, "b0", True, "abrt|f|g", "crash: abrt|f|g")
    _grade(j, "b1", True, "abrt|f|g", "crash: abrt|f|g")      # same fault again
    _grade(j, "b2", True, "segv|h", "crash: segv|h")
    p = json.loads((cell / "score.partial.json").read_text())
    assert p["in_progress"] is True and p["blobs_written"] == 3
    assert p["unique_crashes"] == 2


def test_preserve_pocs_off_still_streams_progress(tmp_path):
    cell = tmp_path / "cell"
    j = _judge(cell, preserve=False)
    _grade(j, "b0", True, "abrt|f|g", "crash: abrt|f|g")
    assert not (cell / "pocs").exists()
    assert (cell / "progress.jsonl").read_text().strip()


def test_a_reporting_failure_never_breaks_grading(tmp_path):
    """The judge's job is the verdict; reporting is strictly secondary."""
    cell = tmp_path / "cell"
    j = _judge(cell)
    j.cell_dir = Path("/proc/nowhere/at/all")     # every write will fail
    _grade(j, "b0", True, "abrt|f|g", "crash: abrt|f|g")
    assert j.log[-1]["crashed"] is True           # grading still recorded


# ------------------------------------------------------------- the trace bridge
# The agent has posted trace requests since the tool was written and nothing
# ever answered: 18 calls across the recorded D5 runs gave 8 timeouts and zero
# reports, because no branch of this bench carried a responder.

def _tj(tmp_path, image="img:latest"):
    ws = tmp_path / "ws"
    j = Judge(ws, Path("/nonexistent"), image=image)
    for d in (j.req, j.res, j.blobs, j.treq, j.tres):
        d.mkdir(parents=True, exist_ok=True)
    return j


def test_the_gdb_script_emits_what_the_agent_parses(tmp_path):
    """The agent keys on `@@REACHED <fn>@@`, then args, then a backtrace."""
    j = _tj(tmp_path)
    script = j._gdb_script("fu_cab_firmware_parse")
    assert "break fu_cab_firmware_parse" in script
    assert "@@REACHED fu_cab_firmware_parse@@" in script
    assert "info args" in script and "\nbt\n" in script
    assert "run /tmp/_cand.bin" in script


def test_a_target_that_is_not_a_symbol_is_refused(tmp_path):
    """The target reaches a shell; it must not be able to carry anything else."""
    j = _tj(tmp_path)
    (j.treq / "r.bin").write_bytes(b"x")
    for bad in ("foo; rm -rf /", "$(id)", "a b", "`whoami`", "--opt"):
        out = j._run_gdb(j.treq / "r.bin", bad)
        assert out.startswith("error: refusing to break on"), bad


def test_a_request_with_no_image_fails_fast(tmp_path):
    j = _tj(tmp_path, image=None)
    (j.treq / "r.bin").write_bytes(b"x")
    assert "no challenge image" in j._run_gdb(j.treq / "r.bin", "main")


def test_a_missing_input_is_reported_not_crashed_on(tmp_path):
    j = _tj(tmp_path)
    assert "no input file" in j._run_gdb(j.treq / "absent.bin", "main")


def test_the_responder_answers_and_clears_the_request(tmp_path, monkeypatch):
    """The loop must write a result and tidy up, whatever gdb did."""
    import threading, time
    j = _tj(tmp_path)
    monkeypatch.setattr(Judge, "_run_gdb",
                        lambda self, blob, target: f"@@REACHED {target}@@\nNo arguments.")
    threading.Thread(target=j._serve_trace, daemon=True).start()
    (j.treq / "rid1.bin").write_bytes(b"x")
    (j.treq / "rid1.tgt").write_text("some_fn")      # written last = ready
    for _ in range(100):
        if (j.tres / "rid1").exists() and not (j.treq / "rid1.bin").exists():
            break
        time.sleep(0.05)
    j._stop.set()
    assert (j.tres / "rid1").read_text().startswith("@@REACHED some_fn@@")
    assert not (j.treq / "rid1.bin").exists() and not (j.treq / "rid1.tgt").exists()


def test_a_slow_gdb_is_claimed_immediately_so_it_is_not_mistaken_for_silence(tmp_path, monkeypatch):
    """The agent gives up on an unclaimed request; a long run must not look unclaimed."""
    import threading, time
    j = _tj(tmp_path)
    started = threading.Event()

    def slow(self, blob, target):
        started.set()
        time.sleep(1.5)
        return f"@@REACHED {target}@@"

    monkeypatch.setattr(Judge, "_run_gdb", slow)
    threading.Thread(target=j._serve_trace, daemon=True).start()
    (j.treq / "rid2.bin").write_bytes(b"x")
    (j.treq / "rid2.tgt").write_text("slow_fn")
    assert started.wait(5), "responder never picked the request up"
    time.sleep(0.2)
    assert not (j.treq / "rid2.tgt").exists(), "request must be claimed before the slow part"
    j._stop.set()


# ------------------------------------------------------------- the turn budget
# Every arm is budgeted the same way: a turn cap and a wall clock, no dollar cap.
# The api arm bounds its own loop; claudecode passes --max-turns to the CLI and
# trusts it. An external agent is the same shape, so it gets the same contract.

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
    assert "_run_agent(argv, str(ws), env, timeout_s, agent_log)" in src
    assert "timeout_s + " not in src, "the wall clock must be handed over intact"


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


def test_the_opening_does_not_stop_the_agent_at_its_first_crash():
    # It used to end "Keep going until one crashes", naming the first crash as
    # the finish line while the api arm was told to find as many as it could.
    # Scoring is min(3, distinct) x difficulty, so that was worth up to two
    # thirds of a cell -- and the bare model produced exactly one crash on 22 of
    # 77 challenges.
    from fbbench.sweep.external import DEFAULT_OPENING
    assert "until one crashes" not in DEFAULT_OPENING
    assert "as many distinct" in DEFAULT_OPENING
    assert "different vulnerabilities" in DEFAULT_OPENING


def test_the_opening_says_the_verdict_is_the_evidence():
    # The api arm is told "an input you have not run through it does not count".
    # An agent that trusts its own harness over the graded one is jq-01: 77 exec
    # calls, one submission, thirty minutes, nothing.
    from fbbench.sweep.external import DEFAULT_OPENING
    assert "not submitted does not count" in DEFAULT_OPENING
    assert "ground truth" in DEFAULT_OPENING


def test_coverage_reach_parses_a_hit_without_a_debugger(tmp_path, monkeypatch):
    # The reach tool used to need gdb inside the challenge image, and half the
    # images ship none. Every libFuzzer target is built with coverage
    # instrumentation, so -print_coverage=1 answers the same question with
    # nothing extra -- and answers a better one, since it lists what WAS
    # reached rather than confirming a name guessed in advance.
    import subprocess
    from fbbench.sweep.external import Judge
    (tmp_path / "ws" / ".fbbench").mkdir(parents=True)
    blob = tmp_path / "c.bin"; blob.write_bytes(b"x")
    j = Judge(tmp_path / "ws", tmp_path / "bug", image="img")

    out = ("COVERED_FUNC: hits: 1 edges: 3/4 xmlTextReaderRead /src/xmlreader.c:1200\n"
           "COVERED_FUNC: hits: 1 edges: 1/1 xmlFuzzReadString /src/fuzz.c:88\n")
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", out))
    r = j._run_coverage(blob, "xmlTextReaderRead")
    assert r.startswith("REACHED xmlTextReaderRead /src/xmlreader.c:1200")
    assert "2 functions executed" in r

    r2 = j._run_coverage(blob, "somethingElse")
    assert r2.startswith("NOT REACHED somethingElse")
    assert "xmlTextReaderRead" in r2, "a miss must still list what WAS reached"


def test_coverage_reach_declines_when_the_image_cannot_symbolize(tmp_path, monkeypatch):
    # skia-01 collects coverage (cov: 733) but has no working symbolizer, so
    # every line reads "<can not symbolize>". Returning None lets the caller
    # fall back to gdb rather than reporting a confident nothing.
    import subprocess
    from fbbench.sweep.external import Judge
    (tmp_path / "ws" / ".fbbench").mkdir(parents=True)
    blob = tmp_path / "c.bin"; blob.write_bytes(b"x")
    j = Judge(tmp_path / "ws", tmp_path / "bug", image="img")
    unsym = "COVERAGE:\n==9==WARNING: invalid path to external symbolizer!\n"
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 0, "", unsym))
    assert j._run_coverage(blob, "anything") is None
