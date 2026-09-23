"""Which challenge image a run reaches for.

Two sets, one per arm kind:

    docker.io/osanzas/fbbench-challenge-<alias>:latest   the api arm
    docker.io/osanzas/fbbench-agent-<alias>:latest       the agent arms

Same challenge in both -- same source, same harness, same prebuilt binary, byte
for byte, so a golden PoC produces the same signature either way. The agent set
additionally ships gdb and leaves the vulnerable build readable, so a debugger
has something to attach to.

The api arm keeps the published images because its recorded results were
produced there, and they are the baseline the agents are measured against.
"""
from __future__ import annotations

import os
import subprocess

DEFAULT_IMAGE_PREFIX = "docker.io/osanzas/fbbench-challenge-"
AGENT_IMAGE_PREFIX = os.environ.get(
    "FBBENCH_AGENT_IMAGE_PREFIX", "docker.io/osanzas/fbbench-agent-")
DEFAULT_IMAGE_TAG = "latest"


def challenge_image(alias: str, prefix: str = DEFAULT_IMAGE_PREFIX) -> str:
    """The published image for one challenge -- the api arm's environment."""
    return f"{prefix}{alias}:{DEFAULT_IMAGE_TAG}"


def agent_image(alias: str) -> str:
    """The same challenge, in the image set the agent arms run in."""
    return f"{AGENT_IMAGE_PREFIX}{alias}:{DEFAULT_IMAGE_TAG}"


def image_digest(image: str) -> str:
    """The image id a cell ran in, or "" if it cannot be read.

    Recorded per cell so a result can be read knowing its environment.
    """
    try:
        r = subprocess.run(["docker", "image", "inspect", image, "--format", "{{.Id}}"],
                           capture_output=True, text=True, timeout=60)
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def pull_policy(image: str) -> str:
    """"always" for a registry image, "missing" for a locally built one.

    A published image is always re-fetched, so a stale cached :latest cannot
    silently grade a run. A local build has nowhere to be fetched from, and
    --pull=always would fail the run before it started. Docker's own rule for
    telling them apart: the first path segment is a registry only if it
    contains a dot or a colon.
    """
    head = image.split("/")[0]
    return "always" if ("." in head or ":" in head) else "missing"
