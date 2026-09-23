"""One bench MCP server per episode, shared by every agent arm.

Lifted out of `claudecode.py` unchanged, so that the external arm can serve the
SAME tool surface from the SAME server rather than a parallel implementation.
That is the point: an arm is a different agent driving identical tools, not a
different set of tools. Anything that lives here is, by construction, the same
for claudecode, codex and any external agent.

The server is the mcp-server baked into the public challenge image. It is
exposed on a unix socket; `relay.py` is a three-line stdio<->socket shim so a
client that speaks MCP over stdin/stdout needs to know nothing about sockets.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path

from fbbench.images import pull_policy


# ------------------------------------------------------------- the tool set
# What the mcp-server inside every challenge image advertises, and therefore
# everything any arm can call. Verified against a live server, not assumed --
# tests/test_arm_parity.py asks one and fails if it disagrees.
#
# It lives here because all three arms must name the same set. Anything that
# needs a tool list builds it from this and nothing keeps its own copy.
BENCH_TOOL_NAMES = ("setup", "exec", "run_poc_on_harness")

_RESERVED = {"mcp-server", "llvm-symbolizer", "sh", "bash", "env"}
_CACHE_ROOT = os.environ.get(
    "FBBENCH_AGENT_TOOLS_CACHE",
    os.path.join(os.path.expanduser("~"), ".cache", "fbbench", "agent-tools"))
_tools_lock = threading.Lock()



def _rpc(sock_path: str, timeout: float, *calls):
    """Open the episode socket, initialise, make `calls`, return the results."""
    import socket as _socket
    c = _socket.socket(_socket.AF_UNIX)
    c.settimeout(timeout)
    c.connect(sock_path)
    f = c.makefile("rw")
    n = [0]

    def call(method, params):
        n[0] += 1
        f.write(json.dumps({"jsonrpc": "2.0", "id": n[0],
                            "method": method, "params": params}) + "\n")
        f.flush()
        while True:
            line = f.readline()
            if not line:
                return None
            m = json.loads(line)
            if m.get("id") == n[0]:
                return m

    call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                        "clientInfo": {"name": "fbbench", "version": "1"}})
    f.write(json.dumps({"jsonrpc": "2.0",
                        "method": "notifications/initialized", "params": {}}) + "\n")
    f.flush()
    out = [call("tools/call", c_) for c_ in calls]
    c.close()
    return out


def _exec_once(sock_path: str, cmd: str, timeout: float = 120.0) -> str:
    """Run one shell command in the challenge container; "" on any failure."""
    try:
        r = _rpc(sock_path, timeout,
                 {"name": "exec", "arguments": {"cmd": cmd, "timeout_s": 60}})[0]
        sc = ((r or {}).get("result") or {}).get("structuredContent") or {}
        return (sc.get("stdout") or "") + (sc.get("stderr") or "")
    except Exception:  # noqa: BLE001
        return ""


def fetch_setup(sock_path: str, timeout: float = 120.0) -> dict:
    """Call setup() on a running episode server and return its answer.

    The api arm builds its first user turn from this response, because it
    carries what nothing else does -- the sanitizer and its fault family. An
    agent arm cannot be handed that text unless the bench asks for it first, so
    the bench asks, once, before the agent starts. Returns {} on any failure:
    a missing context block degrades the prompt, and must not fail the cell.
    """
    import socket as _socket
    try:
        c = _socket.socket(_socket.AF_UNIX)
        c.settimeout(timeout)
        c.connect(sock_path)
        f = c.makefile("rw")
        n = 0

        def call(method, params):
            nonlocal n
            n += 1
            f.write(json.dumps({"jsonrpc": "2.0", "id": n,
                                "method": method, "params": params}) + "\n")
            f.flush()
            while True:
                line = f.readline()
                if not line:
                    return None
                m = json.loads(line)
                if m.get("id") == n:
                    return m

        call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                            "clientInfo": {"name": "fbbench", "version": "1"}})
        f.write(json.dumps({"jsonrpc": "2.0",
                            "method": "notifications/initialized",
                            "params": {}}) + "\n")
        f.flush()
        r = call("tools/call", {"name": "setup", "arguments": {}})
        c.close()
        out = ((r or {}).get("result") or {}).get("structuredContent")
        return out if isinstance(out, dict) else {}
    except Exception:  # noqa: BLE001
        return {}



ORACLE_HARNESS = "/opt/fbbench/oracle/binaries/vuln/asan/harness"


def probe_environment(sock_path: str, timeout: float = 120.0) -> dict:
    """What this container actually offers an agent: {"gdb": bool, "target": str}.

    Asked, not asserted. A prompt that names a debugger the image does not ship,
    or a path the agent cannot open, costs turns the agent never gets back -- a
    live run once spent 2 of its 12 on a binary the prompt promised and the
    kernel refused. `target` is the empty string when the graded build is not
    readable, and the note then says nothing about it.
    """
    cmd = (f"command -v gdb >/dev/null 2>&1 && echo GDB=1 || echo GDB=0; "
           f"test -r {ORACLE_HARNESS} && echo TARGET=1 || echo TARGET=0")
    out = _exec_once(sock_path, cmd, timeout)
    return {"gdb": "GDB=1" in out, "target": ORACLE_HARNESS if "TARGET=1" in out else ""}


GDB_CONFIG_HOME = "/workspace/.config"
GDB_INIT_PATH = GDB_CONFIG_HOME + "/gdb/gdbinit"


def _source_roots(out: str) -> list[str]:
    """The build-time source prefixes named in the binary's own debug info.

    Every path in it is from the machine that compiled the target, e.g.
    /src/harness/harness.c and /src/avro-asan/lang/c/src/map.c. The first
    component under /src is what has to be remapped.
    """
    roots = []
    for tok in re.split(r"[,\s]+", out):
        # only the start of a path counts: .../lang/c/src/map.c contains "/src/"
        # too, and taking that as a root produced 27 rules where 2 were needed.
        if not tok.startswith("/src/"):
            continue
        parts = tok.split("/")
        if len(parts) < 4:
            continue
        r = "/".join(parts[:3])
        if r not in roots:
            roots.append(r)
    return roots


def install_gdb_source_map(sock_path: str, target: str = "",
                           timeout: float = 180.0) -> list[str]:
    """Let gdb show source, by mapping the build paths onto the staged copy.

    The debug info points at the build machine -- /src/<project>-<san>/... and
    /src/harness/... -- none of which exists here, so every stop printed
    "No such file or directory" instead of the line. The source IS present,
    under /challenge. Derived from the binary rather than assumed, and each
    mapping is kept only if it actually resolves a file.

    Returns the rules installed, empty when there is nothing to map.
    """
    target = target or ORACLE_HARNESS
    out = _exec_once(sock_path, f'gdb -batch -ex "file {target}" '
                                f'-ex "info sources" 2>/dev/null', timeout)
    rules = []
    for root in _source_roots(out):
        for cand in (f"/challenge/{os.path.basename(root)}", "/challenge/src"):
            probe = _exec_once(sock_path, f"test -d {cand} && echo OK", 30.0)
            if "OK" in probe:
                rules.append(f"set substitute-path {root} {cand}")
                break
    if not rules:
        return []
    body = "\n".join(rules)
    _exec_once(sock_path,
               f"mkdir -p {GDB_CONFIG_HOME}/gdb && "
               f"cat > {GDB_INIT_PATH} <<'FBEOF'\n{body}\nFBEOF", 60.0)
    # Verified, not assumed. Writing the file proves nothing: a gdb older than
    # 11 never reads this path, and then the agent gets a debugger that cannot
    # show a line while we report that it can. Ask gdb what it loaded.
    shown = _exec_once(sock_path, 'gdb -batch -ex "show substitute-path" 2>&1', 60.0)
    if not all(r.split()[-2] in shown for r in rules):
        return []
    return rules


def agent_tools_note(env: dict | None = None) -> str:
    """The one line an agent arm's SYSTEM prompt carries and the api arm's does not.

    A bullet, because it belongs in the "How to work" list next to the one about
    the harness binary -- it is a readable copy of that same binary. Built from
    probe_environment(), so it can only name what this container actually has,
    and empty when it has neither.
    """
    env = env or {}
    have_gdb, target = bool(env.get("gdb")), env.get("target") or ""
    if have_gdb and target:
        return (f"- You also have `gdb` and a readable copy of that binary, at "
                f"{target}: you may run it, debug it, and ask it which functions "
                f"an input reached (`-print_coverage=1`).")
    if have_gdb:
        return "- You also have `gdb`."
    if target:
        return (f"- You may also read and run the binary run_poc_on_harness() "
                f"grades against, at {target}.")
    return ""


# The bullet about the graded harness binary. The gdb line goes under it, which
# is where a reader looks for it -- not stranded after the closing instruction.
_TOOLS_ANCHOR = "- Do not build a harness binary;"


def with_agent_tools(prompt: str, env: dict | None = None) -> str:
    """`prompt` with the agent's one extra line in its natural place.

    Inserted under the harness-binary bullet. If that bullet ever moves the line
    still goes in, at the end, rather than being silently dropped -- an agent
    that is not told it has gdb does not use it.
    """
    note = agent_tools_note(env)
    if not note:
        return prompt
    lines = prompt.splitlines()
    for i, line in enumerate(lines):
        if line.startswith(_TOOLS_ANCHOR):
            lines.insert(i + 1, note)
            return "\n".join(lines)
    return prompt + "\n\n" + note


# ---------------------------------------------------------------- the policy
# Fuzzing is forbidden to every agent arm, and screened here so the rule is the
# same for all of them and every attempt is recorded in the cell.
#
# Deliberately narrow. `clang -fsanitize=address` is honest work -- compiling a
# reproducer to read a stack trace. What is blocked is building or DRIVING a
# fuzzer: a second oracle that can disagree with the graded one, and a way to
# spend a budget the api arm cannot.
FUZZ_PATTERNS = [
    (r"-fsanitize=[\w,]*fuzzer", "builds a libFuzzer binary"),
    (r"\bafl-(fuzz|clang|gcc|cc|g\+\+)\b", "AFL"),
    (r"\bhonggfuzz\b", "honggfuzz"),
    (r"\bradamsa\b|\bzzuf\b", "a mutation engine"),
    (r"-max_total_time=", "drives libFuzzer by wall clock"),
    (r"-runs=\s*\d{3,}", "drives libFuzzer for hundreds of runs"),
    (r"-jobs=\s*[1-9]", "runs parallel libFuzzer jobs"),
    (r"\bLLVMFuzzerRunDriver\b", "drives libFuzzer directly"),
]
_FUZZ = [(re.compile(p), why) for p, why in FUZZ_PATTERNS]

REFUSAL = (
    "blocked: {why}, and fuzzing is not available on this benchmark.\n"
    "A local fuzzer is a second oracle that can disagree with the graded one, "
    "and it would spend a budget the model you are measured against cannot "
    "spend. Read the harness, form a hypothesis about a specific sink, and test "
    "it with run_poc_on_harness()."
)


def fuzzing_refusal(cmd: str) -> str | None:
    """Why this command may not run, or None. Same rule for every arm."""
    for rx, why in _FUZZ:
        if rx.search(cmd or ""):
            return REFUSAL.format(why=why)
    return None


# The agent arms' safety net, in the module every agent arm already shares.
#
# The api arm drives its own loop and the bench counts its tokens between
# turns, so it needs none of this and keeps no dollar cap. An agent -- Claude
# Code, codex, or any external one -- is a black box that can run away, so it
# gets a hard ceiling on BOTH axes. Deliberately generous: the recorded cells
# ran 30 minutes and $6-10, so this is a guard against a runaway, not a budget
# the work is meant to feel.
AGENT_WALL_CAP_S = 3600        # 1 hour per challenge
AGENT_USD_CAP = 10.0           # $10 per challenge


class CandidateLog:
    """Every candidate an agent grades, preserved as it grades it.

    Written as each verdict arrives rather than swept from the workspace
    afterwards: a killed run still keeps what it earned, and a sweep would
    grade the agent's own `gen.py` as if it were a PoC.

    Both arms now speak to one mcp-server through one relay, so there is one
    place that sees every run_poc_on_harness call and its verdict. Watching it
    is exact -- it records what the agent actually submitted, not what it left
    behind -- and it is live, so an interrupted episode still owes the reader
    nothing.

    Never raises. Observation must not be able to break a run.
    """

    def __init__(self, cell_dir, work: str, preserve: bool = True):
        self.dir = Path(cell_dir) if cell_dir else None
        self.work = work
        self.preserve = preserve
        self.entries: list[dict] = []
        self.blocked: list[dict] = []   # fuzzing attempts, refused
        self._pending: dict = {}          # jsonrpc id -> candidate path
        self._out_buf = b""
        self._in_buf = b""
        self._progress = None
        self._lock = threading.Lock()

    # -- wire taps ---------------------------------------------------------
    def saw_request(self, chunk: bytes) -> None:
        self._out_buf = self._scan(self._out_buf + chunk, self._on_request)

    def saw_response(self, chunk: bytes) -> None:
        self._in_buf = self._scan(self._in_buf + chunk, self._on_response)

    @staticmethod
    def _scan(buf: bytes, handler) -> bytes:
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                handler(json.loads(line))
            except Exception:  # noqa: BLE001 - a frame we cannot parse is not ours
                pass
        # A frame larger than anything MCP sends is not a frame; drop it rather
        # than grow without bound on a stream we have misread.
        return buf if len(buf) < 8 << 20 else b""

    def _on_request(self, msg: dict) -> None:
        if msg.get("method") != "tools/call":
            return
        params = msg.get("params") or {}
        if not str(params.get("name", "")).endswith("run_poc_on_harness"):
            return
        path = ((params.get("arguments") or {}).get("path") or "")
        if msg.get("id") is not None:
            self._pending[msg["id"]] = str(path)

    def _on_response(self, msg: dict) -> None:
        mid = msg.get("id")
        if mid is None or mid not in self._pending:
            return
        path = self._pending.pop(mid)
        try:
            self._record(path, msg.get("result"))
        except Exception:  # noqa: BLE001
            pass

    # -- persistence -------------------------------------------------------
    def _host_path(self, path: str):
        """The agent names a path inside the container; /workspace is ours."""
        if path.startswith("/workspace/"):
            return Path(self.work) / path[len("/workspace/"):]
        return None

    def _record(self, path: str, result) -> None:
        blob = json.dumps(result) if result is not None else ""
        crashed = ('"crash_novelty"' in blob) or ('"signal": "SIG' in blob)
        # The sanitizer's SUMMARY line names the fault AND where it happened, so
        # two different faults stay two rows in the paper trail. Without it every
        # crash collapsed into one "crash|<unnamed>" row.
        m = re.search(r"SUMMARY:\s*\w*(?:Sanitizer|libFuzzer):\s*([^\\\"]+)", blob)
        signature = (m.group(1).strip() if m else None)
        with self._lock:
            n = len(self.entries) + 1
            entry = {"n": n, "path": path, "crashed": crashed,
                     "signature": signature}
            self.entries.append(entry)
            if self.dir is None:
                return
            src = self._host_path(path)
            if self.preserve and src is not None and src.is_file():
                d = self.dir / "pocs" / ("crashed" if crashed else "clean")
                d.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy(src, d / f"blob-{n:03d}")
                    (d / f"blob-{n:03d}.json").write_text(blob[:200000])
                except OSError:
                    pass
            try:
                if self._progress is None:
                    self.dir.mkdir(parents=True, exist_ok=True)
                    self._progress = open(self.dir / "progress.jsonl", "a")
                self._progress.write(json.dumps(entry) + "\n")
                self._progress.flush()
            except OSError:
                pass

    def close(self) -> None:
        try:
            if self._progress is not None:
                self._progress.close()
        except Exception:  # noqa: BLE001
            pass

    def host_blobs(self) -> list[str]:
        """The submitted candidates that exist on the host, deduplicated,
        oldest first -- what an end-of-run grading pass should look at."""
        out, seen = [], set()
        for e in self.entries:
            h = self._host_path(e["path"])
            if h is not None and h.is_file() and str(h) not in seen:
                seen.add(str(h)); out.append(str(h))
        return out

    def note_blocked(self, cmd: str, why: str) -> None:
        """A refused command. Recorded rather than silently dropped: a result
        should be readable knowing whether the agent reached for a fuzzer."""
        with self._lock:
            self.blocked.append({"n": len(self.blocked) + 1, "cmd": cmd[:2000],
                                 "why": why.splitlines()[0]})
            if self.dir is None:
                return
            try:
                self.dir.mkdir(parents=True, exist_ok=True)
                with open(self.dir / "blocked.jsonl", "a") as f:
                    f.write(json.dumps(self.blocked[-1]) + "\n")
            except OSError:
                pass

    def graded_paths(self) -> list[str]:
        """What the agent actually submitted, in order -- not what it left behind."""
        return [e["path"] for e in self.entries]


_RELAY_SRC = """import os, socket, sys, select
s = socket.socket(socket.AF_UNIX); s.connect(sys.argv[1])
i, o = sys.stdin.buffer, sys.stdout.buffer
while True:
    r, _, _ = select.select([i, s], [], [])
    if i in r:
        b = os.read(i.fileno(), 65536)
        if not b: break
        s.sendall(b)
    if s in r:
        b = s.recv(65536)
        if not b: break
        o.write(b); o.flush()
"""


def _screen_frame(line: bytes, candidates: "CandidateLog | None"):
    """A refusal to send back instead of forwarding, or None to let it through.

    Same rule for every agent arm, applied where every arm passes: an exec that
    builds or drives a fuzzer never reaches the container. The reply is shaped
    like a normal exec result so the agent reads it as output and can act on it,
    rather than as a protocol error it cannot interpret.
    """
    try:
        msg = json.loads(line)
    except Exception:  # noqa: BLE001 - not a frame we understand; pass it on
        return None
    if msg.get("method") != "tools/call":
        return None
    params = msg.get("params") or {}
    if not str(params.get("name", "")).endswith("exec"):
        return None
    cmd = str((params.get("arguments") or {}).get("cmd", ""))
    why = fuzzing_refusal(cmd)
    if why is None:
        return None
    if candidates is not None:
        candidates.note_blocked(cmd, why)
    body = {"stdout": "", "stderr": why, "exit_code": 126}
    return (json.dumps({"jsonrpc": "2.0", "id": msg.get("id"),
                        "result": {"content": [{"type": "text",
                                                "text": json.dumps(body)}],
                                   "structuredContent": body}}) + "\n").encode()


def _start_episode_server(image: str, work: str, root: str,
                          candidates: "CandidateLog | None" = None) -> tuple:
    """Start one mcp-server for the episode and expose it on a unix socket.

    Returns (proc, sock_path, relay_path, thread) — the caller must terminate
    proc when the episode ends.
    """
    import socket as _socket
    import threading

    proc = subprocess.Popen(
        ["docker", "run", "-i", "--rm", f"--pull={pull_policy(image)}",
         "--security-opt", "seccomp=unconfined",
         # The image root is read-only, so gdb cannot be given a $HOME/.gdbinit.
         # /workspace is the one writable path, and gdb 12+ reads
         # $XDG_CONFIG_HOME/gdb/gdbinit -- that is where install_gdb_source_map
         # puts the source mapping.
         "-e", f"XDG_CONFIG_HOME={GDB_CONFIG_HOME}",
         "-v", f"{work}:/workspace", image, "mcp-server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, bufsize=0)

    sock_path = os.path.join(root, "bench.sock")
    relay_path = os.path.join(root, "relay.py")
    with open(relay_path, "w") as f:
        f.write(_RELAY_SRC)

    srv = _socket.socket(_socket.AF_UNIX)
    srv.bind(sock_path)
    srv.listen(1)

    # One long-lived pump for server -> client, writing to whichever session is
    # currently connected. Joining a per-connection reader instead deadlocks:
    # it blocks on the server's stdout after the client has gone.
    state = {"conn": None}

    def _pump_out():
        while True:
            try:
                b = os.read(proc.stdout.fileno(), 65536)
            except OSError:
                return
            if not b:
                return
            if candidates is not None:
                candidates.saw_response(b)
            c = state["conn"]
            if c is not None:
                try:
                    c.sendall(b)
                except OSError:
                    state["conn"] = None

    def _serve():
        while proc.poll() is None:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            state["conn"] = conn
            try:
                pend = b""
                while True:
                    b = conn.recv(65536)
                    if not b:
                        break
                    if candidates is not None:
                        candidates.saw_request(b)
                    # Forward frame by frame, so one can be refused without
                    # reaching the challenge. Chunk-at-a-time forwarding cannot
                    # withhold a single call.
                    pend += b
                    allow = b""
                    while b"\n" in pend:
                        line, pend = pend.split(b"\n", 1)
                        reply = _screen_frame(line, candidates)
                        if reply is not None:
                            conn.sendall(reply)
                        elif line.strip():
                            allow += line + b"\n"
                    if allow:
                        proc.stdin.write(allow)
                        proc.stdin.flush()
            except OSError:
                pass
            state["conn"] = None
            try:
                conn.close()
            except OSError:
                pass

    threading.Thread(target=_pump_out, daemon=True).start()
    threading.Thread(target=_serve, daemon=True).start()
    return proc, sock_path, relay_path, srv
