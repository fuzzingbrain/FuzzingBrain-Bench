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


def sandbox_args() -> list[str]:
    """`docker run` flags for a challenge container. Raises if the guard is missing:
    a sandbox that silently allows fuzzing would score a different benchmark."""
    if not os.path.isfile(NOFUZZ_SO):
        raise FileNotFoundError(
            f"{NOFUZZ_SO} is missing; build it from nofuzz.c (see the header there)")
    return ["--network", "none",
            "-v", f"{NOFUZZ_SO}:{NOFUZZ_IN_CONTAINER}:ro",
            "-e", f"LD_PRELOAD={NOFUZZ_IN_CONTAINER}",
            *sig_rules_args()]
