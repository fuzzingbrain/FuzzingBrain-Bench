"""The `docker run` flags every challenge container gets, whichever arm starts it.

Two of them, both about the container rather than the agent in it:

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
"""
from __future__ import annotations

import os

NOFUZZ_SO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nofuzz.so")
NOFUZZ_IN_CONTAINER = "/opt/fbbench-guard/nofuzz.so"

# What the preload prints when it refuses a run; the relay looks for it to
# record the attempt.
NOFUZZ_REFUSED = "[fbbench] refused: this would start libFuzzer's own fuzzing loop"


def sandbox_args() -> list[str]:
    """`docker run` flags for a challenge container. Raises if the guard is missing:
    a sandbox that silently allows fuzzing would score a different benchmark."""
    if not os.path.isfile(NOFUZZ_SO):
        raise FileNotFoundError(
            f"{NOFUZZ_SO} is missing; build it from nofuzz.c (see the header there)")
    return ["--network", "none",
            "-v", f"{NOFUZZ_SO}:{NOFUZZ_IN_CONTAINER}:ro",
            "-e", f"LD_PRELOAD={NOFUZZ_IN_CONTAINER}"]
