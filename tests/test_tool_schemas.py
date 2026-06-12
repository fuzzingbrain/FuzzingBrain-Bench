"""The API arm must present the Go MCP server's OWN tool list to the model.

The runner used to hand-mirror the six tool schemas, which silently drifted from
the server's `tools/list` (and from the Codex arm, which reads the server
directly). `episode.neutral_tools` now fetches the one canonical list, so both
arms show byte-identical tools. This guards that wiring.

Skipped when bin/mcp-server is not built (CI builds it first via `make`).
"""
import tempfile

import pytest

from fbbench.grading import find_bug
from fbbench.paths import SERVER
from fbbench.runner.episode import neutral_tools
from fbbench.runner.mcp_client import MCPClient

pytestmark = pytest.mark.skipif(not SERVER.exists(), reason="bin/mcp-server not built")

_EXPECTED = {"setup", "exec", "list_directory", "read_file", "write_file", "grade"}


def test_tools_come_from_server():
    bd = find_bug("netsnmp-vacm-parse-npd")
    ws = tempfile.mkdtemp()
    mcp = MCPClient(str(SERVER), bug_dir=str(bd), workspace=ws, oracle_dir=str(bd))
    try:
        mcp.initialize()
        tools = neutral_tools(mcp)
    finally:
        for closer in ("close", "stop", "terminate"):
            if hasattr(mcp, closer):
                try:
                    getattr(mcp, closer)()
                except Exception:
                    pass
                break

    assert {t["name"] for t in tools} == _EXPECTED
    for t in tools:
        # neutral schema the backends consume (inputSchema -> input_schema)
        assert set(t) >= {"name", "description", "input_schema"}, t
        assert t["description"].strip(), f"{t['name']}: empty description from server"
        assert t["input_schema"].get("type") == "object"
