"""run_cell, all the way through, with no docker and no model.

Every component of the external arm had a unit test and the arm still could not
have completed a single cell: the PoC-preservation block read `judge.blobs`, a
directory deleted with the request bridge, so any run with preserve_pocs on --
the default -- raised AttributeError *after* the agent had finished and the
money was spent. Reading the code missed it twice. This is the test that would
not have.

Faked: the docker-backed episode server (an in-process MCP server on a real
unix socket), the in-image grader, and the agent process (a real subprocess
that speaks MCP over the socket, exactly as fb-agent does). Everything else --
staging, the candidate observer, the judge, grading, score.json, progress.jsonl,
pocs/, the transcript and report -- is the shipped code.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from fbbench.sweep import external as ex
from fbbench.sweep.mcp_episode import CandidateLog
from fakebench import FakeBenchServer

CRASHING = b"BOOM"


# --- the agent -------------------------------------------------------------
# A real subprocess, because run_cell launches one and reads its stdout, its
# trace file and its usage file. It writes a candidate, grades it, and reports
# the way the manifest contract says an external agent must.
_AGENT = r'''
import json, os, socket, sys
sock, ws = sys.argv[1], sys.argv[2]
s = socket.socket(socket.AF_UNIX); s.connect(sock)
buf = b""
def call(name, args, mid):
    global buf
    s.sendall((json.dumps({"jsonrpc":"2.0","id":mid,"method":"tools/call",
                           "params":{"name":name,"arguments":args}})+"\n").encode())
    while True:
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            if line.strip():
                m = json.loads(line)
                if m.get("id") == mid:
                    return m.get("result")
        buf += s.recv(65536)

call("exec", {"cmd": "printf 'BOOM' > /workspace/c1"}, 1)
call("exec", {"cmd": "printf 'safe' > /workspace/c2"}, 2)
call("exec", {"cmd": "printf 'BOOM' > /workspace/c3"}, 3)
call("run_poc_on_harness", {"path": "/workspace/c1"}, 4)
call("run_poc_on_harness", {"path": "/workspace/c2"}, 5)
call("run_poc_on_harness", {"path": "/workspace/c3"}, 6)

os.makedirs(os.path.join(ws, ".fbbench"), exist_ok=True)
with open(os.path.join(ws, ".fbagent-trace.jsonl"), "w") as f:
    for i, cmd in enumerate(("printf ... > /workspace/c1", "run_poc_on_harness(/workspace/c1)"), 1):
        f.write(json.dumps({"step": i, "kind": "tool_call", "tool": "exec",
                            "input": {"command": cmd}}) + "\n")
        f.write(json.dumps({"step": i, "kind": "tool_result", "tool": "exec",
                            "is_error": False, "content": "ok"}) + "\n")
with open(os.path.join(ws, ".fbbench", "usage.json"), "w") as f:
    json.dump({"model": "m", "input_tokens": 10, "output_tokens": 5,
               "cache_read_tokens": 0, "cache_write_tokens": 0,
               "input_is_total": False}, f)
print(json.dumps({"turns_used": 2, "stop_reason": "done"}))
'''


@pytest.fixture
def wired(tmp_path, monkeypatch):
    """run_cell with docker and the grader replaced, nothing else."""
    bug_dir = tmp_path / "bugs" / "fake-01"
    bug_dir.mkdir(parents=True)
    monkeypatch.setattr(ex, "find_bug", lambda b: bug_dir)
    monkeypatch.setattr(ex, "_full_scan_alias", lambda p: "fake-01")
    # the arm resolves the AGENT image set now, not the published one
    monkeypatch.setattr(ex, "agent_image", lambda a: "fake/image:latest")
    monkeypatch.setattr(ex, "image_digest", lambda i: "sha256:fake")

    servers = []

    def fake_server(image, work, root, candidates=None):
        os.makedirs(work, exist_ok=True)
        srv = FakeBenchServer(os.path.join(root, "bench.sock"), work,
                              verdict=None, observer=candidates)
        servers.append(srv)

        # The real one grades inside the image; this answers by content, so the
        # observer and the grader agree the way they would in a real cell.
        def handle(msg, _orig=srv._handle):
            p = (msg.get("params") or {})
            if p.get("name") == "run_poc_on_harness":
                path = (p.get("arguments") or {}).get("path", "")
                host = os.path.join(work, os.path.basename(path))
                crashed = os.path.isfile(host) and open(host, "rb").read() == CRASHING
                srv.calls.append((p["name"], p.get("arguments", {})))
                return ({"harness_output": {"exit_code": 1, "signal": "SIGABRT",
                                            "stdout": "", "stderr":
                            "==1==ERROR: AddressSanitizer: heap-buffer-overflow\n"
                            "SUMMARY: AddressSanitizer: heap-buffer-overflow x.c:1 in f"},
                         "crash_novelty": "new", "duration_ms": 9}
                        if crashed else
                        {"harness_output": {"exit_code": 0, "signal": "",
                                            "stdout": "", "stderr": ""},
                         "duration_ms": 3})
            return _orig(msg)
        srv._handle = handle

        class Proc:
            def terminate(self): srv.stop()
            def wait(self, timeout=None): return 0
            def kill(self): srv.stop()
        return Proc(), srv.path, os.path.join(root, "relay.py"), srv.srv

    monkeypatch.setattr(ex, "_start_episode_server", fake_server)

    def fake_grade(bug, blobs, pocs_dir=None):
        sigs, best = set(), None
        for b in blobs:
            if Path(b).read_bytes() == CRASHING:
                sigs.add("heap-buffer-overflow x.c:1 in f")
                best = best or b
            if pocs_dir:
                d = Path(pocs_dir) / ("crashed" if Path(b).read_bytes() == CRASHING else "clean")
                d.mkdir(parents=True, exist_ok=True)
                (d / Path(b).name).write_bytes(Path(b).read_bytes())
        return sigs, best

    monkeypatch.setattr(ex, "_crash_signatures", fake_grade)

    agent_py = tmp_path / "agent.py"
    agent_py.write_text(textwrap.dedent(_AGENT))
    manifest = ex.Manifest(
        {"name": "fake-agent",
         "command": f"{sys.executable} {agent_py} {{mcp_socket}} {{workspace}}"},
        tmp_path)
    return manifest


def test_a_cell_completes_and_leaves_the_paper_trail(wired, tmp_path):
    cell = tmp_path / "cell"
    out = ex.run_cell(cell, "fake-01", "m", timeout_s=60, max_turns=10,
                      manifest=wired, preserve_pocs=True)
    assert out is None or "error" not in out, out

    score = json.loads((cell / "score.json").read_text())
    assert score["unique_crashes"] == 1
    assert score["crash_signatures"] == ["heap-buffer-overflow x.c:1 in f"]
    assert score["grading"] == "in-image"
    assert score["agent"] == "fake-agent"
    assert score["turns_used"] == 2
    # the ten fields report.py and the leaderboard read
    for field in ("bug_id", "model", "seed", "score", "duration_s",
                  "max_turns", "config", "total_usd"):
        assert field in score, field


def test_every_candidate_it_graded_is_preserved_with_its_verdict(wired, tmp_path):
    cell = tmp_path / "cell"
    ex.run_cell(cell, "fake-01", "m", timeout_s=60, max_turns=10,
                manifest=wired, preserve_pocs=True)
    crashed = sorted(p.name for p in (cell / "pocs" / "crashed").glob("*") if p.is_file())
    clean = sorted(p.name for p in (cell / "pocs" / "clean").glob("*") if p.is_file())
    # Each candidate is kept twice on purpose: CandidateLog copies it live as
    # blob-NNN (so a killed run still has it) and the grader copies it again
    # under its own name. What matters is that BOTH crashing candidates are
    # there -- marking only the first is the bug this asserts against.
    assert {"c1", "c3"} <= set(crashed), crashed
    assert "c2" not in crashed and "c2" in clean, (crashed, clean)
    assert len([n for n in crashed if n.startswith("blob-") and not n.endswith(".json")]) == 2
    assert (cell / "best_blob").read_bytes() == CRASHING


def test_progress_is_flushed_as_each_candidate_is_graded(wired, tmp_path):
    cell = tmp_path / "cell"
    ex.run_cell(cell, "fake-01", "m", timeout_s=60, max_turns=10,
                manifest=wired, preserve_pocs=True)
    lines = [json.loads(x) for x in
             (cell / "progress.jsonl").read_text().splitlines() if x.strip()]
    assert len(lines) == 3, lines           # every grading, not just the crashes
    assert [l["crashed"] for l in lines] == [True, False, True]


def test_the_transcript_names_the_fault_it_recorded(wired, tmp_path):
    """judge.log feeds the transcript's summary rows. It used to mark `crashed`
    as `b == best`, so with two crashing candidates only one was recorded --
    unique_crashes stayed right (it comes from the signature set) while every
    row built from judge.log understated the run."""
    cell = tmp_path / "cell"
    ex.run_cell(cell, "fake-01", "m", timeout_s=60, max_turns=10,
                manifest=wired, preserve_pocs=True)
    rows = [json.loads(x) for x in
            (cell / "transcript.jsonl").read_text().splitlines() if x.strip()]
    uniq = [r for r in rows if r.get("event") == "unique_crash"]
    # Both candidates fault the same way here, so ONE row is correct -- but it
    # must name the fault. Before the signature was threaded through, every
    # crash collapsed into "crash|<unnamed>" and the trail said nothing.
    assert uniq, "no crash reached the transcript"
    assert all(r["signature"] != "crash|<unnamed>" for r in uniq), uniq
    assert "heap-buffer-overflow" in uniq[0]["signature"], uniq


def test_the_transcript_and_report_are_rendered(wired, tmp_path):
    cell = tmp_path / "cell"
    ex.run_cell(cell, "fake-01", "m", timeout_s=60, max_turns=10,
                manifest=wired, preserve_pocs=True)
    assert (cell / "transcript.jsonl").is_file()
    assert (cell / "report.html").stat().st_size > 0
    assert (cell / "agent.log").is_file()


def test_preserve_pocs_off_still_scores_and_reports(wired, tmp_path):
    """The flag must not be the difference between a cell and an exception."""
    cell = tmp_path / "cell"
    ex.run_cell(cell, "fake-01", "m", timeout_s=60, max_turns=10,
                manifest=wired, preserve_pocs=False)
    assert json.loads((cell / "score.json").read_text())["unique_crashes"] == 1
