"""The trajectory distiller turns a transcript into one node per tool call and
flags grade() calls whose raw harness output faulted."""
from __future__ import annotations

import json

from fbbench.runner import traj


def _transcript(tmp_path, events):
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return p


def test_build_traj_basic(tmp_path):
    p = _transcript(tmp_path, [
        {"event": "start", "model": "m"},                       # ignored
        {"event": "assistant", "turn": 0, "tool_calls": []},    # ignored
        {"event": "tool_result", "turn": 0, "tool": "setup", "is_error": False,
         "input": {}, "result": {"bug_id": "demo-01"}},
        {"event": "tool_result", "turn": 1, "tool": "read_file", "is_error": False,
         "input": {"path": "/v/harness/h.c"}, "result": {"content": "abc"}},
        {"event": "tool_result", "turn": 2, "tool": "write_file", "is_error": False,
         "input": {"path": "/w/poc.bin", "content": "AAAA"}, "result": {"bytes_written": 4}},
        {"event": "tool_result", "turn": 3, "tool": "grade", "is_error": False,
         "input": {"path": "/w/poc.bin"},
         "result": {"harness_output": {"exit_code": 1, "signal": "ABRT",
                    "stderr": "==1==ERROR: AddressSanitizer: heap-buffer-overflow"}}},
    ])
    nodes = traj.build_traj(p)
    assert [n["tool"] for n in nodes] == ["setup", "read_file", "write_file", "grade"]
    assert nodes[0]["out"] == "bug=demo-01"
    assert nodes[1]["out"] == "3 chars"
    assert nodes[2]["out"] == "4B written"
    # the grade faulted (ASan + signal)
    g = nodes[3]
    assert g["crash"] is True
    assert "AddressSanitizer" in g["out"]
    # node numbering is 1-based and contiguous
    assert [n["n"] for n in nodes] == [1, 2, 3, 4]


def test_clean_grade_is_not_a_crash(tmp_path):
    p = _transcript(tmp_path, [
        {"event": "tool_result", "turn": 5, "tool": "grade", "is_error": False,
         "input": {"path": "/w/x"},
         "result": {"harness_output": {"exit_code": 0, "signal": "",
                    "stderr": "Done 1 runs in 0 second(s)"}}},
    ])
    n = traj.build_traj(p)[0]
    assert n["crash"] is False
    assert n["out"].startswith("exit=0")


def test_tool_error_marked(tmp_path):
    p = _transcript(tmp_path, [
        {"event": "tool_result", "turn": 0, "tool": "read_file", "is_error": True,
         "input": {"path": "/nope"}, "result": {"error": "tool error", "data": "is a directory"}},
    ])
    n = traj.build_traj(p)[0]
    assert n["ok"] is False
    assert "is a directory" in n["out"]


def test_render_md_and_write(tmp_path):
    p = _transcript(tmp_path, [
        {"event": "tool_result", "turn": 0, "tool": "setup", "is_error": False,
         "input": {}, "result": {"bug_id": "demo-01"}},
        {"event": "tool_result", "turn": 1, "tool": "grade", "is_error": False,
         "input": {"path": "/w/x"},
         "result": {"harness_output": {"exit_code": 1, "signal": "",
                    "stderr": 'Exception in thread "main" java.lang.ClassCastException'}}},
    ])
    nodes = traj.write_traj(p, tmp_path, header="demo-01 / gpt-5.5")
    assert (tmp_path / "traj.jsonl").is_file()
    md = (tmp_path / "traj.md").read_text()
    assert "demo-01 / gpt-5.5" in md and "1 faulted" in md
    # jsonl round-trips
    lines = (tmp_path / "traj.jsonl").read_text().splitlines()
    assert len(lines) == len(nodes) == 2
    assert json.loads(lines[1])["crash"] is True
