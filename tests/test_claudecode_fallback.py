"""A claudecode cell never scores another model's work under the model asked for.

Claude Code answers a safety refusal by moving the whole session to a fallback
model (observed: claude-fable-5-1 -> claude-opus-4-8 on json-java-02, scored as
Fable with three crashes Fable never produced). The stream must stop there and
the cell must end as a refusal.
"""
import io
import json
import time

from fbbench.sweep import claudecode as cc


def _events(*evs):
    return "".join(json.dumps(e) + "\n" for e in evs)


def _run(stream: str, tmp_path, model="claude-fable-5-1"):
    log = tmp_path / "stream.jsonl"
    log.write_text(stream)
    # A stand-in for `claude -p`: prints the stream; --model is where the arm reads it.
    argv = ["sh", "-c", f"cat {log}", "x", "--model", model]
    return cc._run_claude_once(argv, io.StringIO(), time.time() + 30)


def _assistant(model, mid, text="working"):
    return {"type": "assistant",
            "message": {"id": mid, "model": model,
                        "content": [{"type": "text", "text": text}]}}


def test_the_refusal_fallback_notice_stops_the_cell(tmp_path):
    st = _run(_events(
        {"type": "system", "subtype": "init", "session_id": "s1"},
        _assistant("claude-fable-5-1", "m1"),
        {"type": "system", "subtype": "model_refusal_fallback",
         "original_model": "claude-fable-5-1", "fallback_model": "claude-opus-4-8",
         "api_refusal_category": "cyber", "request_id": "req_1"},
        _assistant("claude-opus-4-8", "m2", "ASSESSMENT COMPLETE"),
    ), tmp_path)
    assert st["ended"] == "refusal"
    assert st["fallback"] == {"from": "claude-fable-5-1", "to": "claude-opus-4-8",
                              "category": "cyber", "request_id": "req_1"}
    # the fallback model's turn is not counted, nor its claim to be done
    assert st["turns"] == 1 and not st["said_complete"]


def test_a_reply_from_another_model_stops_the_cell_without_the_notice(tmp_path):
    st = _run(_events(_assistant("claude-fable-5-1", "m1"),
                      _assistant("claude-opus-4-8", "m2")), tmp_path)
    assert st["ended"] == "refusal"
    assert st["fallback"]["to"] == "claude-opus-4-8"
    assert st["turns"] == 1


def test_the_requested_model_and_synthetic_messages_run_on(tmp_path):
    st = _run(_events(_assistant("claude-opus-5", "m1"),
                      _assistant("<synthetic>", "m2"),
                      _assistant("claude-opus-5", "m3")), tmp_path, model="claude-opus-5")
    assert st["ended"] == "exited" and st["fallback"] is None
    assert st["turns"] == 3
