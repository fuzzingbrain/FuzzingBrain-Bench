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

import os
import subprocess


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


def _start_episode_server(image: str, work: str, root: str) -> tuple:
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
