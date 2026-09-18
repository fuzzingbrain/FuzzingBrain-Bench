"""The one place that sees what every agent actually submitted.

v1 learned this two different ways: the external arm watched a request
directory and copied each blob as it graded it; claudecode and codex swept the
workspace at the end. The sweep grades `gen.py` as a PoC and a killed run keeps
nothing. Both arms now share one relay, so both get the exact, live answer.
"""
import json
from pathlib import Path

from fbbench.sweep.mcp_episode import CandidateLog


def _call(mid, path):
    return json.dumps({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                       "params": {"name": "mcp__bench__run_poc_on_harness",
                                  "arguments": {"path": path}}}).encode() + b"\n"


def _reply(mid, crashed):
    res = {"harness_output": {"exit_code": 1, "signal": "SIGSEGV" if crashed else ""}}
    if crashed:
        res["crash_novelty"] = "new"
    return json.dumps({"jsonrpc": "2.0", "id": mid, "result": res}).encode() + b"\n"


def _log(tmp_path):
    work = tmp_path / "work"; work.mkdir()
    (work / "c1.bin").write_bytes(b"CRASHME")
    (work / "c2.bin").write_bytes(b"clean")
    (work / "gen.py").write_text("# not a candidate")
    return CandidateLog(tmp_path / "cell", str(work)), work


def test_only_what_the_agent_submitted_is_recorded(tmp_path):
    log, _ = _log(tmp_path)
    log.saw_request(_call(1, "/workspace/c1.bin")); log.saw_response(_reply(1, True))
    log.saw_request(_call(2, "/workspace/c2.bin")); log.saw_response(_reply(2, False))
    # gen.py was never submitted, so it is not a candidate.
    assert log.graded_paths() == ["/workspace/c1.bin", "/workspace/c2.bin"]
    assert [e["crashed"] for e in log.entries] == [True, False]


def test_candidates_are_on_disk_before_the_episode_ends(tmp_path):
    log, _ = _log(tmp_path)
    log.saw_request(_call(1, "/workspace/c1.bin")); log.saw_response(_reply(1, True))
    # No close(), no end-of-run sweep: a killed run must already have this.
    assert (tmp_path / "cell" / "pocs" / "crashed" / "blob-001").read_bytes() == b"CRASHME"
    lines = (tmp_path / "cell" / "progress.jsonl").read_text().strip().split("\n")
    assert json.loads(lines[0])["crashed"] is True
    log.close()


def test_a_clean_verdict_lands_in_clean(tmp_path):
    log, _ = _log(tmp_path)
    log.saw_request(_call(7, "/workspace/c2.bin")); log.saw_response(_reply(7, False))
    assert (tmp_path / "cell" / "pocs" / "clean" / "blob-001").is_file()
    assert not (tmp_path / "cell" / "pocs" / "crashed").exists()
    log.close()


def test_a_frame_split_across_reads_is_still_seen(tmp_path):
    """The pump hands over 64KB chunks, not lines."""
    log, _ = _log(tmp_path)
    raw = _call(1, "/workspace/c1.bin")
    log.saw_request(raw[:12]); log.saw_request(raw[12:])
    log.saw_response(_reply(1, True))
    assert log.graded_paths() == ["/workspace/c1.bin"]
    log.close()


def test_traffic_that_is_not_a_grading_call_is_ignored(tmp_path):
    log, _ = _log(tmp_path)
    log.saw_request(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                "params": {"name": "mcp__bench__exec",
                                           "arguments": {"cmd": "ls"}}}).encode() + b"\n")
    log.saw_response(_reply(1, True))
    log.saw_request(b'not json at all\n')
    assert log.entries == []
    log.close()


def test_a_path_outside_the_shared_workspace_is_recorded_but_not_copied(tmp_path):
    """/tmp inside the container is not visible on the host. Still counts."""
    log, _ = _log(tmp_path)
    log.saw_request(_call(1, "/tmp/scratch.bin")); log.saw_response(_reply(1, True))
    assert log.graded_paths() == ["/tmp/scratch.bin"]
    assert not list((tmp_path / "cell" / "pocs").rglob("blob-*")) 
    log.close()
