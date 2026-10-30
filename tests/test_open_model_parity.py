"""The api arm asks a self-hosted model what FB-Agent asks it.

FB-Agent's Gemma requests (output/fb-agent-gemma-4-*/exchange.jsonl) carry
temperature 1.0, top_p 0.95, top_k 64, thinking on and no output cap, and each
cell holds one server from FBBENCH_AGENT_ENDPOINTS for its whole episode.
"""
from types import SimpleNamespace

from fbbench.runner.backends import make_backend
from fbbench.sweep import orchestrator


def _sent(monkeypatch, model):
    b = make_backend(model)
    seen = {}

    def create(**kw):
        seen.update(kw)
        msg = SimpleNamespace(content="ok", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason="stop")],
                               usage=None)
    monkeypatch.setattr(b._client.chat.completions, "create", create)
    b.complete("sys", [{"role": "user", "content": "hi"}], [], 32000)
    return seen


def test_gemma_gets_fb_agents_sampling(monkeypatch):
    kw = _sent(monkeypatch, "gemma4:31b-qat")
    assert kw["temperature"] == 1.0 and kw["top_p"] == 0.95
    assert kw["extra_body"] == {"top_k": 64,
                                "chat_template_kwargs": {"enable_thinking": True}}
    assert "max_tokens" not in kw and "max_completion_tokens" not in kw


def test_each_local_cell_holds_one_endpoint(monkeypatch, tmp_path):
    monkeypatch.setenv("FBBENCH_AGENT_ENDPOINTS", "http://h:8300/v1,http://h:8301/v1")
    got = []

    def run(cmd, **kw):
        got.append((kw.get("env") or {}).get("OLLAMA_BASE_URL"))
    monkeypatch.setattr(orchestrator.subprocess, "run", run)
    for _ in range(3):
        orchestrator.run_cell("gemma4:31b-qat", "avro-03", 0, 5, tmp_path, 60)
    # released after each cell, so the pool never runs dry or leaks
    assert got[0] in ("http://h:8300/v1", "http://h:8301/v1") and None not in got
    orchestrator.run_cell("claude-haiku-4-5", "avro-03", 0, 5, tmp_path, 60)
    assert got[-1] is None
