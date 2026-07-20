"""Drive the MCP server's grade() oracle on a single blob — no agent, no LLM.

This is the vendor-neutral grading entry point: feed it bytes from any source
(AFL++, libFuzzer, hand-crafted, an LLM episode) and it runs the official
sanitizer-instrumented harness through the same three-round oracle the agent
sees. Consolidates the duplicate subprocess plumbing that fb-bench grade and
the regression smoke test each used to carry.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fbbench.paths import SERVER

FLAGS = ["reach", "crash", "differential", "class", "site"]

# Single source of truth for the remote grading oracle. Developers switch the
# endpoint HERE; every caller references this constant (env BENCH_GRADE_URL
# still overrides at runtime for private/staging oracles).
DEFAULT_GRADE_URL = "https://nonretinal-arletha-arduous.ngrok-free.dev"


def grade_blob(bug_dir: Path, blob: Path, rounds: int = 3,
               server_bin: Path = SERVER, timeout: int = 300) -> tuple[dict, float]:
    """Grade `blob` against `bug_dir`'s oracle.

    Returns (structuredContent, elapsed_s) where structuredContent is the
    grade() result: {capabilities, agreed, rounds, evidence, ...}.
    """
    ws = Path(tempfile.mkdtemp(prefix=f"fb-{Path(bug_dir).name}-"))
    try:
        shutil.copy(blob, ws / "input.bin")
        req = {
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "grade", "arguments": {
                "path": str(ws / "input.bin"),
                "options": {"round_count": rounds},
            }},
        }
        env = os.environ.copy()
        env["BENCH_BUG_DIR"] = str(Path(bug_dir).resolve())
        env["BENCH_WORKSPACE"] = str(ws)
        # The oracle endpoint is internal infrastructure, not a user knob: default
        # it here so host grading reaches the remote oracle without the caller ever
        # setting BENCH_GRADE_URL. An explicit env value still wins (staging/private).
        env.setdefault("BENCH_GRADE_URL", DEFAULT_GRADE_URL)
        t0 = time.time()
        p = subprocess.run([str(server_bin)],
                           input=(json.dumps(req) + "\n").encode(),
                           capture_output=True, env=env, timeout=timeout)
        elapsed = time.time() - t0
        lines = p.stdout.decode().strip().splitlines()
        if not lines:
            stderr = p.stderr.decode().strip().splitlines()
            tail = stderr[-1] if stderr else "(no output)"
            raise RuntimeError(f"grade oracle produced no response: {tail}")
        out = json.loads(lines[-1])
        # The server reports failures as a JSON-RPC error object, not a `result`.
        # Surface its real message (e.g. "BENCH_BUG_ID must be set for remote
        # grading") instead of letting `out["result"]` blow up as KeyError('result').
        if "error" in out:
            err = out["error"] or {}
            msg = err.get("data") or err.get("message") or err
            raise RuntimeError(f"grade oracle error: {msg}")
        return out["result"]["structuredContent"], elapsed
    finally:
        shutil.rmtree(ws, ignore_errors=True)
