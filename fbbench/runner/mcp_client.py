"""Line-delimited JSON-RPC 2.0 client for the FuzzingBrain Bench MCP server.

The server is a Go subprocess; we talk over its stdin/stdout. This is a
narrow shim — just enough to drive the 6-tool contract.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Any

import yaml

# URLs in staged harness sources (e.g. a "see issues/5946" comment) point the
# agent at the upstream bug report. Network egress is already blocked, but we
# also redact the link text from the agent's view so it gets no pointer at all.
_URL_RE = re.compile(rb'https?://[^\s"\'<>)\]]+')

# Entries copied into the agent-facing sandbox bug view. Everything else in
# the real bug dir — grader/ (answer key), poc/ (reference solution), and
# binaries/ (ground-truth builds) — is deliberately withheld: the agent
# reasons from harness source and tests via grade(), which runs the trusted
# binaries from the oracle dir server-side.
#
# Deliberately NOT staged (they leak the solution):
#   - PROVENANCE.md  : discovery notes, root cause, exact crash site.
#   - Dockerfile     : `git clone <repo> && git checkout <vuln_commit>` — hands
#                      the agent the upstream repo+commit (the agent never
#                      builds; grade() uses the pre-built oracle binaries).
SANDBOX_ENTRIES = ("description.txt", "bench.yaml", "harness")

# Files stripped from any staged subtree (e.g. harness/PROVENANCE.md).
SANDBOX_IGNORE = ("PROVENANCE.md",)

# bench.yaml keys withheld from the agent: they identify the upstream report /
# repo / commit, which an agent could use to look up the fix or reference PoC.
# Everything the oracle needs at runtime (harness.*, capability_set) is kept.
_BENCH_SCRUB_TOP = ("upstream_report", "cve")
_BENCH_SCRUB_TARGET = ("repo", "vuln_commit")


def _ignore_leaky(_dir: str, names: list[str]) -> list[str]:
    return [n for n in names if n in SANDBOX_IGNORE]


def _redact_urls_in_tree(root: str) -> None:
    """Redact http(s) URLs from text files under a staged subtree."""
    for dirpath, _, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            try:
                with open(p, "rb") as fp:
                    data = fp.read()
            except OSError:
                continue
            if b"http://" not in data and b"https://" not in data:
                continue
            new = _URL_RE.sub(b"[redacted-url]", data)
            if new != data:
                with open(p, "wb") as fp:
                    fp.write(new)


def _full_scan_alias(real_bug_dir: str) -> str:
    """A neutral `<project>-NN` handle for full-scan, replacing the descriptive
    bug_id (e.g. `libpng-zlib-inflate-uaf` -> `libpng-03`) so the identifier no
    longer names the bug. NN is the bug's stable 1-based position among its
    project's bundles (sorted). The project name is not a leak — the harness
    source reveals it anyway."""
    real = os.path.abspath(real_bug_dir)
    proj_dir = os.path.dirname(real)
    project = os.path.basename(proj_dir)
    me = os.path.basename(real)
    siblings = sorted(n for n in os.listdir(proj_dir)
                      if os.path.isfile(os.path.join(proj_dir, n, "bench.yaml")))
    idx = (siblings.index(me) + 1) if me in siblings else 1
    return f"{project}-{idx:02d}"


def _stage_bench_yaml(src: str, dst: str, full_scan: bool = False,
                      alias: str | None = None) -> None:
    """Copy bench.yaml with upstream/repo/commit identifiers stripped.

    In full_scan mode the fields that name or categorize the bug are also removed:
    `title` (names the class + function), `capability_set` (reveals the fault
    class — e.g. no `crash` => a leak), and the descriptive `bug_id` is replaced
    by a neutral `<project>-NN` alias. Otherwise these would hand back the very
    description full_scan is meant to withhold.
    """
    data = yaml.safe_load(open(src)) or {}
    for k in _BENCH_SCRUB_TOP:
        data.pop(k, None)
    if full_scan:
        for k in ("title", "disclosed", "capability_set", "notes"):
            data.pop(k, None)
        if alias:
            data["bug_id"] = alias
        else:
            data.pop("bug_id", None)
    tgt = data.get("target")
    if isinstance(tgt, dict):
        for k in _BENCH_SCRUB_TARGET:
            tgt.pop(k, None)
    with open(dst, "w") as fp:
        yaml.safe_dump(data, fp, sort_keys=False)


def stage_bug_view(real_bug_dir: str, full_scan: bool = False) -> str:
    """Build a per-episode sandbox dir holding only agent-safe entries.

    Returns the sandbox path; the caller passes it as BENCH_BUG_DIR and the
    real bug dir as BENCH_ORACLE_DIR. Withheld: grader/, poc/, binaries/,
    PROVENANCE.md, Dockerfile, and upstream/repo/commit fields of bench.yaml.

    full_scan mode additionally withholds description.txt and, from bench.yaml,
    the title / capability_set / notes, and replaces the descriptive bug_id with
    a neutral `<project>-NN` alias — the agent gets only the harness (the fuzz
    target) and must discover the fault with no statement of what or where it is.
    """
    sandbox = tempfile.mkdtemp(prefix="fbbench-bugview-")
    # mkdtemp is 0700; the agent's exec() may run under a different uid
    # (Tier 2 privsep), so make the view traversable/readable.
    os.chmod(sandbox, 0o755)
    alias = _full_scan_alias(real_bug_dir) if full_scan else None
    entries = SANDBOX_ENTRIES
    if full_scan:
        entries = tuple(e for e in entries if e != "description.txt")
    for name in entries:
        src = os.path.join(real_bug_dir, name)
        if not os.path.exists(src):
            continue
        dst = os.path.join(sandbox, name)
        if name == "bench.yaml":
            _stage_bench_yaml(src, dst, full_scan=full_scan, alias=alias)
        elif os.path.isdir(src):
            shutil.copytree(src, dst, ignore=_ignore_leaky)
            _redact_urls_in_tree(dst)
        else:
            shutil.copy2(src, dst)
    return sandbox


class MCPClient:
    def __init__(self, server_bin: str, bug_dir: str, workspace: str,
                 oracle_dir: str | None = None):
        env = os.environ.copy()
        env["BENCH_BUG_DIR"] = bug_dir
        env["BENCH_WORKSPACE"] = workspace
        # Grader reads expected.yaml + binaries from the oracle dir; the agent
        # never sees it. Defaults to bug_dir for back-compat when unset.
        env["BENCH_ORACLE_DIR"] = oracle_dir or bug_dir
        self._proc = subprocess.Popen(
            [server_bin],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            bufsize=0,
        )
        self._id = 0
        self._lock = threading.Lock()
        self.bug_dir = bug_dir
        self.workspace = workspace
        # Drain stderr to a buffer so the pipe never fills.
        self._stderr_buf: list[bytes] = []
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _drain_stderr(self) -> None:
        assert self._proc.stderr is not None
        for line in self._proc.stderr:
            self._stderr_buf.append(line)

    def initialize(self) -> dict:
        return self._call("initialize", {})

    def list_tools(self) -> list[dict]:
        return self._call("tools/list", {})["tools"]

    def call(self, name: str, arguments: dict) -> Any:
        resp = self._call("tools/call", {"name": name, "arguments": arguments})
        return resp.get("structuredContent", resp)

    def _call(self, method: str, params: dict) -> dict:
        with self._lock:
            self._id += 1
            req = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params}
            assert self._proc.stdin is not None
            self._proc.stdin.write((json.dumps(req) + "\n").encode())
            self._proc.stdin.flush()
            assert self._proc.stdout is not None
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("MCP server closed stdout; stderr=" + b"".join(self._stderr_buf[-20:]).decode("utf-8", "replace"))
            resp = json.loads(line)
        if "error" in resp:
            err = resp["error"]
            raise MCPToolError(err.get("message", "tool error"), err.get("data"))
        return resp["result"]

    def close(self) -> None:
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except Exception:
            pass
        try:
            self._proc.terminate()
            self._proc.wait(timeout=5)
        except Exception:
            self._proc.kill()


class MCPToolError(Exception):
    def __init__(self, message: str, data: Any = None):
        super().__init__(message)
        self.data = data
