"""The `docker run` flags every challenge container gets, whichever arm starts it.

Three of them, all about the container rather than the agent in it:

--network none
    Nothing in a challenge container needs the network. exec() already runs
    in its own empty net namespace; the grader does not, and ASan's symbolizer,
    started by the graded harness, makes a name lookup. With the host behind a
    VPN whose DNS does not answer the docker bridge, that lookup hangs until
    the harness timeout: every crash then took 3 x 40 s to grade and came back
    with no frames -- no stack for the agent, and a `<unsigned>` signature that
    collapses distinct crashes into one. Measured on dtc-01: 121 s with the
    bridge, 1 s without. No network makes the result independent of the host's.

nofuzz.so, preloaded
    Fuzzing is not what the benchmark measures. The relay's text screen
    (mcp_episode.FUZZ_PATTERNS) catches the obvious invocations; it cannot see
    a harness started with no input, which is libFuzzer's fuzzing loop by
    default -- one agent found leak inputs that way in seconds. The preload
    refuses that inside every libFuzzer process, however it was started. See
    nofuzz.c.

the scoring rules, mounted
    The grader in each image names crashes with the signature rules baked in
    when the image was built. Only the api arm used to mount this checkout's
    copy over them, so a rules change reached it and not the agent arms, and
    two arms could count the same crashes differently. Every arm gets the same
    rules from here. See `sig_rules_args`.
"""
from __future__ import annotations

import os

# This checkout's crash-signature rules, and where they are mounted so the
# in-image grader uses them. See `sig_rules_args`.
SIG_RULES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "grading", "signature.py")
SIG_RULES_IN_CONTAINER = "/opt/fbbench/signature.current.py"


def sig_rules_args() -> list[str]:
    """`docker run` flags making the in-image grader score with THIS checkout's
    crash-signature rules instead of the copy baked into the image.

    A self-contained image grades locally, and names each crash with the
    signature script `build_challenge` vendored into it when the image was
    built. That copy is frozen at build time, so a rules fix reaches a published
    image only by rebuilding and republishing all of them — and until it does,
    the image counts distinct crashes by one set of rules while everything
    downstream reads them by another. Mounting the current file closes that gap
    for every runner-driven episode, which is what a sweep is.

    Read-only, and deliberately so: the agent has exec in this container, and a
    writable scoring rule is one `printf` away from every crash being novel.

    Two things this does NOT cover, both by nature. An image driven directly by
    an external user gets its baked copy — nothing here runs for them. And the
    baked copy is what an external user gets, so the two still have to be moved
    together; this only removes runner-driven episodes from that list.

    Set BENCH_SIG_SCRIPT on the host to override (including to the baked path,
    to measure exactly what an external user would get).
    """
    if os.environ.get("BENCH_SIG_SCRIPT"):
        return ["-e", f"BENCH_SIG_SCRIPT={os.environ['BENCH_SIG_SCRIPT']}"]
    if not os.path.isfile(SIG_RULES):
        # Better to grade with the baked rules than to mount nothing at the path
        # we then point the server at: a missing script makes every crash
        # `<unsigned>`, which silently collapses them all into one.
        return []
    return ["-v", f"{SIG_RULES}:{SIG_RULES_IN_CONTAINER}:ro",
            "-e", f"BENCH_SIG_SCRIPT={SIG_RULES_IN_CONTAINER}"]


NOFUZZ_SO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nofuzz.so")
NOFUZZ_IN_CONTAINER = "/opt/fbbench-guard/nofuzz.so"

# What the preload prints when it refuses a run; the relay looks for it to
# record the attempt.
NOFUZZ_REFUSED = "[fbbench] refused: this would start libFuzzer's own fuzzing loop"


# --no-debugging-tool: the same setting with the debugger taken away -- gdb on a
# native target, jdb on a JVM one (no challenge has both) -- for measuring what it
# is worth. Set by the CLI for the whole run, so every container of every arm
# sees it; read here and in mcp_episode.probe_environment, and nowhere else.
NO_DEBUGGING_TOOL_ENV = "FBBENCH_NO_DEBUGGING_TOOL"
DEBUGGER_STUB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "debugging-tool-unavailable.sh")
# jdb and jdb-run exist only in the JVM agent images (tools/jdb); mounting the stub
# where a native image has no such file just leaves a stub there.
DEBUGGER_PATHS = ("/usr/bin/gdb", "/usr/bin/gdbtui", "/usr/bin/jdb", "/usr/local/bin/jdb-run")


def no_debugging_tool() -> bool:
    return os.environ.get(NO_DEBUGGING_TOOL_ENV) == "1"


# --no-callgraph: the same setting with the static call graph taken away. The
# mcp-server in the image reads BENCH_NO_CALLGRAPH and then neither advertises
# the call-graph tools nor answers `cg`; probe_environment reports it absent, so
# the tools note says nothing about it. Read here and there, nowhere else.
NO_CALLGRAPH_ENV = "FBBENCH_NO_CALLGRAPH"
NO_CALLGRAPH_CONTAINER_ENV = "BENCH_NO_CALLGRAPH"
# The shell entry is a wrapper script in the image (tools/callgraph/Dockerfile),
# so a stub can be mounted over it the way gdb's is; the server does not pass
# the env switch on to the agent's shell, so the mount is what takes `cg` away.
CG_STUB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cg-unavailable.sh")
CG_PATH = "/usr/local/bin/cg"


def no_callgraph() -> bool:
    return os.environ.get(NO_CALLGRAPH_ENV) == "1"


# Host-local, not part of the benchmark: on a machine shared with other pinned
# workloads, FBBENCH_AVOID_CONTAINERS=<name prefix> keeps every challenge container
# off the CPUs (and their hyperthread siblings) those containers are pinned to,
# read afresh at each container start. Unset, nothing changes.
AVOID_CONTAINERS_ENV = "FBBENCH_AVOID_CONTAINERS"


def _parse_cpuset(spec: str) -> set[int]:
    out: set[int] = set()
    for part in filter(None, spec.split(",")):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def cpuset_args() -> list[str]:
    prefix = os.environ.get(AVOID_CONTAINERS_ENV)
    if not prefix:
        return []
    import subprocess
    ids = subprocess.run(["docker", "ps", "-q", "--filter", f"name=^{prefix}"],
                         capture_output=True, text=True).stdout.split()
    busy: set[int] = {0}
    if ids:
        specs = subprocess.run(["docker", "inspect", "--format",
                                "{{.HostConfig.CpusetCpus}}", *ids],
                               capture_output=True, text=True).stdout.split()
        for spec in specs:
            busy |= _parse_cpuset(spec)
    n = os.cpu_count() or 1
    half = n // 2
    busy |= {(c + half) % n for c in busy}
    free = [c for c in range(n) if c not in busy]
    return ["--cpuset-cpus", ",".join(map(str, free))] if free else []


MEMORY_ENV = "FBBENCH_CONTAINER_MEMORY"


def memory_args() -> list[str]:
    """A per-container memory cap (e.g. "8g") from the environment, so a runaway
    PoC is OOM-killed inside its own container instead of taking down the host."""
    mem = os.environ.get(MEMORY_ENV, "").strip()
    return ["--memory", mem, "--memory-swap", mem] if mem else []


def sandbox_args() -> list[str]:
    """`docker run` flags for a challenge container. Raises if the guard is missing:
    a sandbox that silently allows fuzzing would score a different benchmark."""
    if not os.path.isfile(NOFUZZ_SO):
        raise FileNotFoundError(
            f"{NOFUZZ_SO} is missing; build it from nofuzz.c (see the header there)")
    return ["--network", "none",
            *cpuset_args(),
            *memory_args(),
            "-v", f"{NOFUZZ_SO}:{NOFUZZ_IN_CONTAINER}:ro",
            "-e", f"LD_PRELOAD={NOFUZZ_IN_CONTAINER}",
            *sig_rules_args(),
            *[a for p in (DEBUGGER_PATHS if no_debugging_tool() else ())
              for a in ("-v", f"{DEBUGGER_STUB}:{p}:ro")],
            *(["-e", f"{NO_CALLGRAPH_CONTAINER_ENV}=1", "-v", f"{CG_STUB}:{CG_PATH}:ro"]
              if no_callgraph() else [])]
