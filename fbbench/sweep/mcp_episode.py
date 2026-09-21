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


# ------------------------------------------------------------- the agent tools
# Where v2 differs from v1 on purpose: an AGENT arm may be given tools the bare
# api arm does not have. gdb is the first and deliberately not the last.
#
# The binaries come from a PINNED IMAGE, not from a directory someone fills in.
# That is the whole point: a gitignored bin/ means a second machine runs a
# different benchmark and nothing says so. Pull one image by digest and every
# machine has identical bits, while the challenge images stay untouched.
#
#   tools image  ->  cache dir on this host  ->  bind-mounted file by file
#                    (derived, disposable)       into /usr/local/bin
#
# File by file, never as a directory: /usr/local/bin holds the challenge's own
# mcp-server and llvm-symbolizer, and mounting over it would hide them.
#
# The api arm starts its own container through MCPClient and never calls this,
# so it is untouched by construction rather than by a flag.
#
# Binaries in the image must be STATICALLY linked -- the gdb the challenge
# images ship is 10 MB against 59 shared libraries and will not start anywhere
# else.
DEFAULT_AGENT_TOOLS_IMAGE = "osanzas/fbbench-agent-tools:v1"
"""The published toolbox. Pulled automatically the first time an agent episode
starts on a machine, then cached, so gdb is not something anyone installs,
configures or is told about -- it is part of the benchmark."""

_tools_env = os.environ.get("FBBENCH_AGENT_TOOLS_IMAGE")
AGENT_TOOLS_IMAGE = (
    DEFAULT_AGENT_TOOLS_IMAGE if _tools_env is None else _tools_env.strip())
if AGENT_TOOLS_IMAGE.lower() in {"none", "off", "0", ""}:
    AGENT_TOOLS_IMAGE = ""
"""Override to pin a digest (`...@sha256:...`) or point at your own registry.
Set it to `none` to run an agent arm with only what the challenge image ships."""


class AgentToolsUnavailable(RuntimeError):
    """The toolbox was asked for and could not be had.

    Raised rather than quietly continuing. An agent arm that silently loses gdb
    still produces a number, and that number is not comparable to one produced
    with it -- on 33 of the 78 challenges the agent would have no debugger at
    all. A run that cannot be compared is worse than a run that stops."""

_RESERVED = {"mcp-server", "llvm-symbolizer", "sh", "bash", "env"}
_CACHE_ROOT = os.environ.get(
    "FBBENCH_AGENT_TOOLS_CACHE",
    os.path.join(os.path.expanduser("~"), ".cache", "fbbench", "agent-tools"))
_tools_lock = threading.Lock()


def agent_tools_digest(image: str | None = None) -> str:
    """The image id, so a cell can record WHICH toolbox it ran with."""
    img = AGENT_TOOLS_IMAGE if image is None else image
    if not img:
        return ""
    try:
        r = subprocess.run(["docker", "image", "inspect", img, "--format", "{{.Id}}"],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def ensure_agent_tools(image: str | None = None) -> str:
    """Materialise the toolbox for this host and return its directory.

    Cached per image id, so the copy happens once per machine per version and a
    version bump repopulates rather than silently reusing stale binaries.
    """
    img = AGENT_TOOLS_IMAGE if image is None else image
    if not img:
        return ""
    with _tools_lock:
        digest = agent_tools_digest(img)
        if not digest:
            try:
                pull = subprocess.run(["docker", "pull", "-q", img],
                                      capture_output=True, text=True, timeout=1800)
            except Exception as e:  # noqa: BLE001
                raise AgentToolsUnavailable(
                    f"could not pull the agent toolbox {img}: {e}") from e
            digest = agent_tools_digest(img)
            if not digest:
                raise AgentToolsUnavailable(
                    f"could not pull the agent toolbox {img}.\n"
                    f"  docker said: {(pull.stderr or pull.stdout or '').strip()[:300]}\n"
                    f"  This machine would run the agent arms without gdb, which is\n"
                    f"  not comparable to a run that had it. Fix the pull, or set\n"
                    f"  FBBENCH_AGENT_TOOLS_IMAGE=none to accept that deliberately.")
        d = os.path.join(_CACHE_ROOT, digest.replace(":", "_"))
        stamp = os.path.join(d, ".complete")
        if os.path.exists(stamp):
            return os.path.join(d, "bin")
        os.makedirs(os.path.join(d, "bin"), exist_ok=True)
        # `docker create` + `docker cp`, not `docker run`: the toolbox image is
        # FROM scratch and holds nothing but the binaries -- no shell, no cp,
        # nothing to run. `create` only registers a container, so the command
        # given here is never executed, and `cp` reads the filesystem from the
        # outside. Copying with `docker run ... sh -c cp` would fail on every
        # machine, which is exactly the class of breakage this image exists to
        # avoid.
        cid = ""
        try:
            c = subprocess.run(["docker", "create", img, "/nonexistent"],
                               capture_output=True, text=True, timeout=300)
            cid = (c.stdout or "").strip()
            if c.returncode != 0 or not cid:
                raise AgentToolsUnavailable(
                    f"could not open the agent toolbox {img}: "
                    f"{(c.stderr or '').strip()[:300]}")
            r = subprocess.run(
                ["docker", "cp", f"{cid}:/tools/bin/.", os.path.join(d, "bin")],
                capture_output=True, text=True, timeout=1800)
            if r.returncode != 0:
                raise AgentToolsUnavailable(
                    f"could not copy the agent toolbox out of {img}: "
                    f"{(r.stderr or '').strip()[:300]}")
            for name in os.listdir(os.path.join(d, "bin")):
                f = os.path.join(d, "bin", name)
                if os.path.isfile(f):
                    os.chmod(f, 0o755)
            open(stamp, "w").close()
        except AgentToolsUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            raise AgentToolsUnavailable(
                f"could not materialise the agent toolbox {img}: {e}") from e
        finally:
            if cid:
                subprocess.run(["docker", "rm", "-f", cid],
                               capture_output=True, timeout=300)
        return os.path.join(d, "bin")


def agent_tool_mounts(tools_dir: str | None = None) -> tuple[list[str], list[str]]:
    """(docker -v arguments, tool names) for the agent toolbox."""
    d = ensure_agent_tools() if tools_dir is None else tools_dir
    args: list[str] = []
    names: list[str] = []
    if not d:
        return args, names
    try:
        entries = sorted(os.listdir(d))
    except OSError:
        return args, names
    for name in entries:
        src = os.path.join(d, name)
        if not os.path.isfile(src) or not os.access(src, os.X_OK):
            continue
        if name in _RESERVED or name.startswith("."):
            continue
        args += ["-v", f"{src}:/usr/local/bin/{name}:ro"]
        names.append(name)
    return args, names


# ---------------------------------------------------------------- the policy
# Fuzzing is forbidden to EVERY agent arm, and the bench is where that belongs.
# It used to live in fb-agent's own coach, which meant one arm was refused a
# tool the others were free to use -- a rule asymmetry on top of a tooling one.
# Screening it here also makes it visible: a run that tried is recorded, so a
# result can be read knowing whether the agent reached for it.
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

    The bench used to learn what an agent tried in two different ways. The
    external arm watched a request directory and copied each blob out the
    moment it was graded; claudecode and codex swept the workspace afterwards
    and graded whatever files happened to be lying there. The second is worse
    twice over: a killed run keeps nothing, and a workspace sweep grades the
    agent's `gen.py` as if it were a PoC.

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
        ["docker", "run", "-i", "--rm", "--pull=always",
         "--security-opt", "seccomp=unconfined",
         "-v", f"{work}:/workspace", *agent_tool_mounts()[0], image, "mcp-server"],
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
