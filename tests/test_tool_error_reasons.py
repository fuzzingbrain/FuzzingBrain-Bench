"""A failed tool call reaches every client with its reason, not just "tool error"."""
import json

from fbbench.sweep.mcp_episode import _explain_tool_error


def _err(mid, data):
    return (json.dumps({"jsonrpc": "2.0", "id": mid,
                        "error": {"code": -32000, "message": "tool error", "data": data}})
            + "\n").encode()


def _text(line):
    r = json.loads(line)["result"]
    assert r["isError"] is True
    return r["content"][0]["text"]


def test_a_path_outside_the_workspace_says_so_and_names_the_path():
    out = _explain_tool_error(_err(7, "grade target must live under BENCH_WORKSPACE"),
                              {7: "/tmp/poc.bin"})
    assert _text(out) == "error: the input must be a file under /workspace (got /tmp/poc.bin)"


def test_a_grade_outside_the_workspace_is_not_told_challenge_is_allowed():
    out = _explain_tool_error(_err(6, "permission denied"), {6: "/tmp/poc.bin"})
    assert _text(out) == "error: the input must be a file under /workspace (got /tmp/poc.bin)"


def test_a_missing_file_says_so():
    out = _explain_tool_error(
        _err(8, "grade target not found or is a directory: /workspace/nope"), {8: "/workspace/nope"})
    assert _text(out) == "error: no such file, or it is a directory (got /workspace/nope)"


def test_an_unknown_reason_is_passed_through_in_the_agents_paths():
    out = _explain_tool_error(_err(9, "cannot stage candidate in BENCH_WORKSPACE"), {})
    assert _text(out) == "error: cannot stage candidate in /workspace"


def test_everything_else_is_untouched():
    ok = b'{"jsonrpc": "2.0", "id": 1, "result": {"structuredContent": {"exit_code": 0}}}\n'
    assert _explain_tool_error(ok, {}) == ok
    other = (json.dumps({"jsonrpc": "2.0", "id": 2,
                         "error": {"code": -32601, "message": "method not found"}}) + "\n").encode()
    assert _explain_tool_error(other, {}) == other
