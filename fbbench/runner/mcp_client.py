"""Line-delimited JSON-RPC 2.0 client for the FuzzingBrain Bench MCP server.

The server is a Go subprocess; we talk over its stdin/stdout. This is a
narrow shim — just enough to drive the 6-tool contract.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from typing import Any

import yaml

from fbbench.paths import REPO

# Cached library-source checkouts (repo @ vuln_commit), shared across episodes.
# gitignored (under runs/). Each entry is the source tree at the buggy commit
# with .git removed, so the agent can read/grep the real (vulnerable) code but
# cannot walk history to the fix.
# Library-source cache is mode-NEUTRAL (full-scan / normal / diff all stage it),
# so it lives at runs/_srccache, not under diffscan/.
SRCCACHE = REPO / "runs" / "_srccache"

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


def _ensure_source_cache(repo: str, commit: str) -> str | None:
    """Clone repo@commit (blobless), strip .git, cache it. Returns the cache
    path, or None if the source can't be fetched. One-time per (repo, commit)."""
    if not repo or not commit:
        return None
    key = hashlib.sha1(f"{repo}@{commit}".encode()).hexdigest()[:16]
    cache = SRCCACHE / key
    if (cache / ".ready").exists():
        return str(cache)
    SRCCACHE.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="srcclone-", dir=str(SRCCACHE))
    try:
        # blobless clone keeps the fetch small; checkout pulls only this commit's
        # blobs. --no-checkout first so we control which commit lands.
        subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout",
                        "--quiet", repo, tmp], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        # vuln_commit is not always a sha: it can be a fork branch name
        # (fwupd -> origin/<branch>) or a release/version label (graaljs
        # "24.1.2" -> tag graal-24.1.2). Resolve to something checkout-able.
        ref = _resolve_ref(tmp, commit)
        if ref is None:
            raise ValueError(f"ref {commit!r} not found (not a sha/branch/tag)")
        subprocess.run(["git", "-C", tmp, "checkout", "--quiet", "--detach", ref],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=600)
        shutil.rmtree(os.path.join(tmp, ".git"), ignore_errors=True)
        open(os.path.join(tmp, ".ready"), "w").close()
        try:
            os.replace(tmp, cache)   # atomic same-fs move into place
        except OSError:
            # Another worker populated this same (repo, commit) concurrently
            # (many bugs share a repo). Theirs is fine — drop ours.
            shutil.rmtree(tmp, ignore_errors=True)
        return str(cache) if (cache / ".ready").exists() else None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError,
            ValueError) as e:
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"[stage_source] could not fetch {repo}@{commit}: {e}", flush=True)
        return None


def _resolve_ref(repo_dir: str, commit: str) -> str | None:
    """Resolve vuln_commit to a checkout-able ref: a sha/tag as-is, else a fork
    branch (origin/<name>), else a tag whose name ends with the version label
    (e.g. "24.1.2" -> "graal-24.1.2")."""
    def ok(r: str) -> bool:
        return subprocess.run(
            ["git", "-C", repo_dir, "rev-parse", "--verify", "--quiet", r + "^{commit}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    if ok(commit):
        return commit
    if ok("origin/" + commit):
        return "origin/" + commit
    tags = subprocess.run(["git", "-C", repo_dir, "tag", "--list"],
                          capture_output=True, text=True).stdout.split()
    matches = [t for t in tags if t.endswith(commit)]
    return matches[0] if matches else None


def _stage_source(real_bug_dir: str, sandbox: str) -> None:
    """Stage the library source (repo @ vuln_commit) into <sandbox>/src/ so the
    agent can read/grep the real vulnerable code. Infrastructure-provided — the
    agent never clones or reaches the network itself. Best-effort: if the source
    can't be fetched the episode still runs (no src/)."""
    if os.environ.get("BENCH_STAGE_SOURCE", "1") == "0":
        return
    try:
        bench = yaml.safe_load(open(os.path.join(real_bug_dir, "bench.yaml"))) or {}
    except OSError:
        return
    tgt = bench.get("target", {}) or {}
    cache = _ensure_source_cache(tgt.get("repo", ""), tgt.get("vuln_commit", ""))
    if not cache:
        return
    dst = os.path.join(sandbox, "src")
    os.makedirs(dst, exist_ok=True)
    # hardlink-copy (cheap, shares inodes) when same fs; else a plain copy.
    if subprocess.run(["cp", "-al", cache + "/.", dst + "/"],
                      stderr=subprocess.DEVNULL).returncode != 0:
        subprocess.run(["cp", "-a", cache + "/.", dst + "/"], stderr=subprocess.DEVNULL)


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


# Source files whose leading block comment is stripped in full-scan (it often
# names the bug region / CVE cluster). Inline comments that explain the INPUT
# FORMAT are kept — the agent legitimately needs them to craft an input.
_SRC_EXTS = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh", ".java")
_ENTRYPOINT_MARKERS = ("LLVMFuzzerTestOneInput", "fuzzerTestOneInput")

# Neutral description.txt staged in full-scan so setup() returns this (and not the
# server's "re-trigger the documented crash" synthDescription fallback). Names
# nothing about the bug.
_FULLSCAN_DESC_NOTICE = (
    "FULL-SCAN MODE — no bug description is provided.\n\n"
    "You are given only the fuzz harness (the target). A fault is reachable "
    "through it (a memory-safety crash, a reachable assertion, a memory leak, or "
    "an out-of-memory / oversized allocation), but you are not told which it is or "
    "where it lives. Read the harness to learn the input shape, craft an input, and "
    "use grade() to test it.\n"
)


def _strip_leading_comment(text: str) -> str:
    """Drop a leading run of blank lines / // lines / /* ... */ blocks (the
    license + descriptive header) up to the first real code line. Comments
    further down (e.g. input-layout notes next to the parsing code) are kept."""
    lines = text.split("\n")
    i, n = 0, len(lines)
    while i < n:
        s = lines[i].strip()
        if s == "" or s.startswith("//"):
            i += 1
            continue
        if s.startswith("/*"):
            while i < n and "*/" not in lines[i]:
                i += 1
            i += 1  # consume the line containing */
            continue
        break
    return "\n".join(lines[i:]).lstrip("\n")


def _neutralize_harness(harness_dir: str) -> None:
    """full-scan: strip leading header comments from staged harness sources and
    rename the entrypoint file to a neutral `harness.<ext>` (e.g.
    `vp9_encoder_midstream_reconfig_fuzzer.cc` -> `harness.cc`). The filename and
    header are pure hints; the code itself (the fuzzed API) is left intact because
    the agent needs it to know the input shape. build.sh and helper files keep
    their names; only their header comment is stripped."""
    if not os.path.isdir(harness_dir):
        return
    for root, _, files in os.walk(harness_dir):
        for fn in files:
            if fn == "build.sh" or os.path.splitext(fn)[1] not in _SRC_EXTS:
                continue
            p = os.path.join(root, fn)
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            stripped = _strip_leading_comment(txt)
            if stripped != txt:
                with open(p, "w") as fp:
                    fp.write(stripped)
    # Rename the single entrypoint source to harness.<ext>.
    for root, _, files in os.walk(harness_dir):
        for fn in sorted(files):
            ext = os.path.splitext(fn)[1]
            if ext not in (".c", ".cc", ".cpp", ".cxx", ".java"):
                continue
            p = os.path.join(root, fn)
            try:
                txt = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            if any(m in txt for m in _ENTRYPOINT_MARKERS):
                new = os.path.join(root, "harness" + ext)
                if os.path.abspath(new) != os.path.abspath(p) \
                        and not os.path.exists(new):
                    os.rename(p, new)
                return


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
            if full_scan and name == "harness":
                _neutralize_harness(dst)
        else:
            shutil.copy2(src, dst)
    if full_scan:
        # Stage a NEUTRAL description.txt rather than leaving none. Without it the
        # MCP server's setup() falls back to synthDescription(), which emits
        # "...reconstruct the bug from ... the upstream report ... re-trigger the
        # documented crash" — a framing that leaks back to the agent when it calls
        # setup() itself. A present (neutral) file suppresses that fallback.
        with open(os.path.join(sandbox, "description.txt"), "w") as fp:
            fp.write(_FULLSCAN_DESC_NOTICE)
    # Stage the real (vulnerable) library source as infrastructure — all modes.
    _stage_source(real_bug_dir, sandbox)
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
