"""The static call graph: the counterpart of gdb in the agent image.

/challenge/callgraph.sqlite + four tools on the same mcp-server + `cg` in the
shell. These tests hold the pieces together without a container: the Go and
Python tool lists, the --no-callgraph switch, the tools note, and the converter
that produces the file the image ships.
"""
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from fbbench import sandbox
from fbbench.sweep import claudecode as cc
from fbbench.sweep.mcp_episode import (
    BENCH_TOOL_NAMES, CALLGRAPH_NOTE, CALLGRAPH_PATH, CALLGRAPH_TOOL_NAMES,
    ORACLE_HARNESS, agent_tools_note)

ROOT = Path(__file__).resolve().parents[1]
GO_SRC = ROOT / "tools" / "mcp-server" / "callgraph.go"
CONVERTER = ROOT / "tools" / "callgraph" / "build_sqlite.py"


def test_go_and_python_name_the_same_tools():
    src = GO_SRC.read_text()
    m = re.search(r'CallgraphToolNames = \[\]string\{([^}]*)\}', src)
    assert m, "CallgraphToolNames not found in callgraph.go"
    go_names = tuple(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert go_names == CALLGRAPH_TOOL_NAMES
    assert re.search(r'callgraphDefaultPath\s*=\s*"%s"' % re.escape(CALLGRAPH_PATH), src)
    assert re.search(r'callgraphDisableEnv\s*=\s*"%s"' % sandbox.NO_CALLGRAPH_CONTAINER_ENV, src)
    assert not set(CALLGRAPH_TOOL_NAMES) & set(BENCH_TOOL_NAMES)


def test_claude_code_may_call_them_and_has_their_names_prefixed():
    for t in CALLGRAPH_TOOL_NAMES:
        assert f"mcp__bench__{t}" in cc._BENCH_TOOLS.split(",")
    env = {"gdb": False, "native": False, "target": "", "callgraph": True}
    p = cc.claude_task_prompt({}, env)
    # the opening (first user turn) is the api arm's and names no call-graph tool
    assert "get_callers" not in p


def test_switch_off_by_default(monkeypatch):
    monkeypatch.delenv(sandbox.NO_CALLGRAPH_ENV, raising=False)
    assert not sandbox.no_callgraph()
    assert not any(sandbox.NO_CALLGRAPH_CONTAINER_ENV in a or "cg-unavailable" in a
                   for a in sandbox.sandbox_args())


def test_switch_reaches_the_container(monkeypatch):
    monkeypatch.setenv(sandbox.NO_CALLGRAPH_ENV, "1")
    args = sandbox.sandbox_args()
    i = args.index(f"{sandbox.NO_CALLGRAPH_CONTAINER_ENV}=1")
    assert args[i - 1] == "-e"
    # and the shell entry is replaced, like gdb's: the switch does not reach the
    # agent's shell environment, the mount is what takes `cg` away
    assert f"{sandbox.CG_STUB}:{sandbox.CG_PATH}:ro" in args
    assert os.access(sandbox.CG_STUB, os.X_OK)


def test_the_note_is_one_bullet_added_under_the_dynamic_one():
    t = ORACLE_HARNESS
    base = {"gdb": True, "native": True, "target": t}
    without = agent_tools_note(base)
    with_cg = agent_tools_note({**base, "callgraph": True})
    assert with_cg == without + "\n" + CALLGRAPH_NOTE
    assert CALLGRAPH_NOTE.startswith("- ")
    for tool in CALLGRAPH_TOOL_NAMES:
        assert f"{tool}()" in CALLGRAPH_NOTE
    assert "cg " in CALLGRAPH_NOTE
    # nothing else moved: the gdb note is byte-identical with or without the graph
    assert agent_tools_note(base) == without
    # a JVM image (no gdb, no native binary) still gets the graph alone
    assert agent_tools_note({"gdb": False, "native": False, "target": t, "callgraph": True}).endswith(CALLGRAPH_NOTE)
    assert "callgraph" not in agent_tools_note({}) and agent_tools_note({}) == ""


def _toy_graph(tmp_path: Path) -> Path:
    def node(name, file, line, end):
        return {"id": f"{name}@{os.path.basename(file)}:{line}", "name": name, "file": file,
                "line": line, "line_end": end, "content": f"int {name}() {{}}"}
    nodes = [node("LLVMFuzzerTestOneInput", "harness.c", 10, 20),
             node("parse", "lib/parse.c", 5, 60),
             node("helper", "lib/util.c", 1, 9),
             node("helper", "lib/other.c", 1, 9),      # same name, other file
             node("orphan", "lib/dead.c", 3, 4)]
    edges = [["LLVMFuzzerTestOneInput@harness.c:10", "parse@parse.c:5"],
             ["parse@parse.c:5", "helper@util.c:1"],
             ["parse@parse.c:5", "helper@util.c:1"],   # second call site, one edge
             ["orphan@dead.c:3", "helper@other.c:1"],
             ["parse@parse.c:5", "missing@nowhere.c:1"]]
    g = {"meta": {"challenge": "toy-01", "lang": "c", "method": "test",
                  "entry": "LLVMFuzzerTestOneInput@harness.c:10", "n_nodes": 5, "n_edges": 5,
                  "edges_resolved": 5, "edges_byname": 0, "issues": []},
         "nodes": nodes, "edges": edges}
    p = tmp_path / "toy-01.graph.json"
    p.write_text(json.dumps(g))
    return p


def test_converter_builds_the_contract(tmp_path):
    src = _toy_graph(tmp_path)
    out = tmp_path / "toy-01.callgraph.sqlite"
    r = subprocess.run([sys.executable, "-I", str(CONVERTER), str(src), "-o", str(out)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect(f"file:{out}?mode=ro&immutable=1", uri=True)
    meta = dict(db.execute("SELECT key, value FROM meta"))
    assert meta["schema_version"] == "1"
    assert meta["challenge"] == "toy-01"
    assert meta["entry"] == "LLVMFuzzerTestOneInput@harness.c:10"
    assert meta["n_functions"] == "5"
    assert meta["n_calls"] == "3", "duplicate call site collapsed, dangling edge dropped"
    assert meta["reachable_from_entry"] == "3"
    assert "1 edges to unknown nodes dropped" in meta["issues"]
    # depth/parent: entry 0, parse 1, helper@util 2 with parent parse; the rest -1
    rows = {uid: (d, p) for uid, d, p in db.execute("SELECT uid, depth, parent FROM functions")}
    assert rows["LLVMFuzzerTestOneInput@harness.c:10"][0] == 0
    assert rows["parse@parse.c:5"][0] == 1
    parse_id, = db.execute("SELECT id FROM functions WHERE uid='parse@parse.c:5'").fetchone()
    assert rows["helper@util.c:1"] == (2, parse_id)
    assert rows["helper@other.c:1"][0] == -1 and rows["orphan@dead.c:3"][0] == -1
    # content is NOT shipped
    assert "content" not in [c[1] for c in db.execute("PRAGMA table_info(functions)")]
    # indexes the tools rely on exist
    idx = {r[1] for r in db.execute("PRAGMA index_list(calls)")}
    assert {"calls_caller", "calls_callee"} <= idx
    # --check agrees with itself
    r = subprocess.run([sys.executable, "-I", str(CONVERTER), "--check", str(out)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.rstrip().endswith("OK"), r.stdout


@pytest.mark.skipif(not (ROOT / "tools" / "mcp-server" / "go.mod").exists(), reason="no Go source")
def test_binary_answers_as_cg_when_go_is_available(tmp_path):
    """Build the server and ask it the four questions on the toy graph. Skipped
    where Go is not installed; the container test covers the image."""
    import shutil
    if not shutil.which("go"):
        pytest.skip("go not installed")
    out = tmp_path / "toy-01.callgraph.sqlite"
    subprocess.run([sys.executable, "-I", str(CONVERTER), str(_toy_graph(tmp_path)), "-o", str(out)],
                   check=True, capture_output=True, timeout=60)
    binary = tmp_path / "mcp-server"
    b = subprocess.run(["go", "build", "-o", str(binary), "."], cwd=ROOT / "tools" / "mcp-server",
                       capture_output=True, text=True, timeout=600,
                       env={**os.environ, "CGO_ENABLED": "0", "GOTOOLCHAIN": "local"})
    if b.returncode != 0:
        pytest.skip(f"go build failed here: {b.stderr[-300:]}")
    env = {**os.environ, "BENCH_CALLGRAPH": str(out)}

    def cg(*args):
        r = subprocess.run([str(binary), "cg", *args], capture_output=True, text=True, timeout=30, env=env)
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else None), r.stderr

    rc, res, _ = cg("callees", "parse")
    assert rc == 0 and [f["name"] for f in res["callees"]] == ["helper"] and res["total"] == 1
    rc, res, _ = cg("callers", "helper")
    assert rc == 0 and res["ambiguous"] and len(res["candidates"]) == 2
    rc, res, _ = cg("callers", "helper", "util.c")
    assert rc == 0 and [f["name"] for f in res["callers"]] == ["parse"]
    rc, res, _ = cg("path", "helper", "lib/util.c")
    assert rc == 0 and res["reachable"] and [f["name"] for f in res["path"]] == \
        ["LLVMFuzzerTestOneInput", "parse", "helper"] and res["depth"] == 2
    rc, res, _ = cg("path", "orphan")
    assert rc == 0 and res["reachable"] is False
    rc, res, _ = cg("callers", "nope")
    assert rc == 0 and "no function named" in res["error"]
    rc, res, _ = cg("sql", "SELECT count(*) FROM functions WHERE depth >= 0")
    assert rc == 0 and res["rows"] == [[3]]
    for bad in ("DELETE FROM functions", "PRAGMA table_info(functions)", "SELECT 1; SELECT 2",
                "WITH x AS (SELECT 1) SELECT * FROM x; ATTACH 'a' AS b"):
        rc, _, err = cg("sql", bad)
        assert rc == 1, bad
    # the switch: the same binary says it has nothing
    r = subprocess.run([str(binary), "cg", "info"], capture_output=True, text=True, timeout=30,
                       env={**env, sandbox.NO_CALLGRAPH_CONTAINER_ENV: "1"})
    assert r.returncode == 1 and "no call graph" in r.stderr
    # and the MCP tool list follows the switch
    def tools(extra_env):
        msgs = '{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
        r = subprocess.run([str(binary)], input=msgs, capture_output=True, text=True, timeout=30,
                           env={**env, "BENCH_BUG_DIR": str(tmp_path), "BENCH_WORKSPACE": str(tmp_path / "ws"), **extra_env})
        return [t["name"] for t in json.loads(r.stdout.splitlines()[0])["result"]["tools"]]
    assert tuple(tools({})) == BENCH_TOOL_NAMES + CALLGRAPH_TOOL_NAMES
    assert tuple(tools({sandbox.NO_CALLGRAPH_CONTAINER_ENV: "1"})) == BENCH_TOOL_NAMES
