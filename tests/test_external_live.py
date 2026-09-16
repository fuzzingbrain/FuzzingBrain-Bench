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
    t0 = _time.time()
    out, _err, timed_out = _run_agent([_sys.executable, "-c", prog], ".", None, 2)
    elapsed = _time.time() - t0
    assert timed_out
    assert elapsed < 5, elapsed
    # What the agent printed before the kill is still returned, not discarded.
    assert "started" in out


def test_an_agent_that_finishes_early_is_not_charged_the_clock():
    import sys as _sys
    import time as _time
    from fbbench.sweep.external import _run_agent
    t0 = _time.time()
    out, _err, timed_out = _run_agent(
        [_sys.executable, "-c", "print('done')"], ".", None, 60)
    assert not timed_out
    assert "done" in out
    assert _time.time() - t0 < 10


def test_no_grace_period_is_added_to_the_agent_wall_clock():
    import inspect
    from fbbench.sweep import external
    src = inspect.getsource(external.run_cell)
    assert "_run_agent(argv, str(ws), env, timeout_s)" in src
    assert "timeout_s + " not in src, "the wall clock must be handed over intact"
