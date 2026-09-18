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
                while True:
                    b = conn.recv(65536)
                    if not b:
                        break
                    if candidates is not None:
                        candidates.saw_request(b)
                    proc.stdin.write(b)
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
