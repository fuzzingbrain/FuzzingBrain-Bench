"""Which challenge image a run reaches for.

There are two image sets, one per arm kind:

    docker.io/osanzas/fbbench-challenge-<alias>:latest   the api arm
    fbbench-agent/<alias>:latest                         the agent arms

They hold the SAME challenge -- same source, same harness, same prebuilt
binary, byte for byte, so a golden PoC produces the same signature in both.
They differ in two deliberate ways: the agent image ships gdb, and it leaves
the vulnerable build readable so a debugger has something to attach to.

Why two sets rather than one. gdb shipped in 12 of the 24 images surveyed and
was absent from the other 12, and the graded binary was openable in exactly
those same 12 -- both facts decided by which build script last touched the
image, not by anything anyone chose. An agent arm cannot be evaluated on a
corpus where half the challenges silently have a debugger. Giving the api arm
the same treatment would invalidate the v1 baseline every agent is measured
against, because those numbers were produced inside the published images. So
the baseline keeps its images untouched and the agents get a uniform set.

This replaces the v2 workaround, which bind-mounted a statically linked gdb and
a readable copy of the target into the published images at container start. That
worked, and it was the right thing while the images could not be rebuilt -- but
it could not fix what the images themselves lacked.

It carries its own sanitizer harness and grades every candidate inside the
container, with no network. It counts the distinct crash signatures the agent
produced, and that count is the score.

Nothing infers anything from the tag. There is one grader — the image's own —
and the episode records that it answered, as ``config.grading``.
"""
from __future__ import annotations

DEFAULT_IMAGE_PREFIX = "docker.io/osanzas/fbbench-challenge-"
# The agent image set. Local-only until it is published; override to point at a
# registry once it is.
import os
AGENT_IMAGE_PREFIX = os.environ.get("FBBENCH_AGENT_IMAGE_PREFIX", "fbbench-agent/")
# One published tag. It was configurable while the tag chose a grader -- :latest
# graded remotely, :local-v1 in-image -- and there is nothing left for it to
# select, so it is a constant rather than a flag nobody can usefully set.
DEFAULT_IMAGE_TAG = "latest"


def challenge_image(alias: str, prefix: str = DEFAULT_IMAGE_PREFIX) -> str:
    """The published image for one challenge -- the api arm's environment."""
    return f"{prefix}{alias}:{DEFAULT_IMAGE_TAG}"


def agent_image(alias: str) -> str:
    """The same challenge, in the image set the AGENT arms run in."""
    return f"{AGENT_IMAGE_PREFIX}{alias}:{DEFAULT_IMAGE_TAG}"


def image_digest(image: str) -> str:
    """The image id a cell actually ran in, or "" if it cannot be read.

    Recorded per cell so a number can be read knowing the environment that
    produced it. This replaces agent_tools_digest, which identified the gdb
    toolbox the bench used to mount in; the environment is the image now, so
    the image is what a result should name.
    """
    import subprocess
    try:
        r = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""
