"""Fuzzing is forbidden to every agent arm, by the bench, and it is recorded.

It used to live in fb-agent's own coach: one arm refused a tool the others were
free to use -- a rule asymmetry sitting on top of the tooling one this branch
removed. It belongs where every arm passes, which is the shared relay.
"""
import json

import pytest

from fbbench.sweep.mcp_episode import (
    CandidateLog, _screen_frame, fuzzing_refusal)


def _frame(cmd, name="mcp__bench__exec", mid=1):
    return json.dumps({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                       "params": {"name": name, "arguments": {"cmd": cmd}}}).encode()


BLOCKED = [
    "clang -fsanitize=fuzzer,address harness.c -o h",
    "afl-fuzz -i in -o out -- ./target @@",
    "honggfuzz -f in -- ./target",
    "./h -max_total_time=600 corpus/",
    "./h -runs=1000000 corpus/",
    "./h -jobs=8 corpus/",
]
ALLOWED = [
    "clang -fsanitize=address repro.c -o repro",   # honest: read a stack trace
    "gdb -batch -ex run ./h /workspace/c1",
    "ls -la /challenge/src",
    "python3 -c \"open('/workspace/c1','wb').write(b'x')\"",
]


@pytest.mark.parametrize("cmd", BLOCKED)
def test_a_fuzzer_never_reaches_the_container(cmd):
    reply = _screen_frame(_frame(cmd), None)
    assert reply is not None, "this would have run"
    body = json.loads(reply)["result"]["structuredContent"]
    assert body["exit_code"] == 126
    assert "fuzzing is not available" in body["stderr"]
    # A refusal that does not say what to do instead wastes the turn.
    assert "run_poc_on_harness()" in body["stderr"]


@pytest.mark.parametrize("cmd", ALLOWED)
def test_honest_work_is_not_refused(cmd):
    assert fuzzing_refusal(cmd) is None, cmd
    assert _screen_frame(_frame(cmd), None) is None


def test_the_rule_applies_whatever_the_arm_calls_the_tool():
    """claudecode sends mcp__bench__exec, an MCP client sends exec."""
    for name in ("exec", "mcp__bench__exec"):
        assert _screen_frame(_frame("afl-fuzz -i i -o o -- ./t", name), None) is not None


def test_an_attempt_is_recorded_for_the_run_results(tmp_path):
    log = CandidateLog(tmp_path / "cell", str(tmp_path))
    _screen_frame(_frame("clang -fsanitize=fuzzer h.c"), log)
    _screen_frame(_frame("ls /challenge"), log)
    assert len(log.blocked) == 1
    line = json.loads((tmp_path / "cell" / "blocked.jsonl").read_text().strip())
    assert "fsanitize=fuzzer" in line["cmd"]
    assert "libFuzzer" in line["why"]


def test_traffic_that_is_not_an_exec_passes_untouched():
    grade = json.dumps({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                        "params": {"name": "run_poc_on_harness",
                                   "arguments": {"path": "/workspace/c1"}}}).encode()
    assert _screen_frame(grade, None) is None
    assert _screen_frame(b"not json", None) is None
    assert _screen_frame(b'{"method":"initialize","id":1}', None) is None


def test_both_arms_report_the_attempt_count_in_score_json():
    """Screened 'in the future run results' means a field, not a log line."""
    import inspect
    from fbbench.sweep import claudecode as cc, external as ex
    assert '"fuzzing_attempts"' in inspect.getsource(ex.run_cell)
    assert '"fuzzing_attempts"' in inspect.getsource(cc._persist)


def test_the_ban_is_the_bench_s_and_not_one_arm_s():
    """fb-agent's coach must no longer be the only thing enforcing it -- a rule
    one arm carries and the others do not is the asymmetry, not the fix."""
    import inspect
    from fbbench.sweep import mcp_episode as ep
    assert ep.FUZZ_PATTERNS, "the patterns live in the shared module"
    assert "fuzzing_refusal" in inspect.getsource(ep._screen_frame)
