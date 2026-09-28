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
    """"always" for a registry image, "missing" for a locally built one or for
    one `prepull` already fetched for this run.

    A published image is always re-fetched, so a stale cached :latest cannot
    silently grade a run. A local build has nowhere to be fetched from, and
    --pull=always would fail the run before it started. Docker's own rule for
    telling them apart: the first path segment is a registry only if it
    contains a dot or a colon.
    """
    if image in PREPULLED:
        return "missing"
    head = image.split("/")[0]
    return "always" if ("." in head or ":" in head) else "missing"


# Images fetched by `prepull` at the start of this process's run.
PREPULLED: set[str] = set()


def prepull(images, attempts: int = 3, log=print) -> list[str]:
    """Fetch every image a run will use before its first cell; the ones that
    could not be fetched are returned.

    Otherwise a cell fetched its image as it started, and the fetch happened in
    the time the agent had to connect to its challenge: in the 77-challenge
    Qwen run a 1.5 GB image (icu-02) came down so slowly that the agent timed
    out before its first turn and scored a zero that said nothing about the
    model. Fetched here, a cell starts on an image already on disk.

    It also pins the run to one version of each image. A fetched image is
    started with --pull=missing from then on (see `pull_policy`), so an image
    republished halfway through a sweep cannot grade its later cells
    differently from its earlier ones.
    """
    import time as _t
    failed = []
    todo = [i for i in dict.fromkeys(images) if i not in PREPULLED]
    for n, image in enumerate(todo, 1):
        t0 = _t.time()
        for attempt in range(attempts):
            r = subprocess.run(["docker", "pull", "-q", image],
                               capture_output=True, text=True)
            if r.returncode == 0:
                PREPULLED.add(image)
                log(f"  prepull [{n}/{len(todo)}] {image} ({_t.time() - t0:.0f}s)")
                break
            if attempt + 1 < attempts:
                _t.sleep(2 * (attempt + 1))
        else:
            failed.append(image)
            log(f"  prepull [{n}/{len(todo)}] FAILED {image}: {(r.stderr or '').strip()[-200:]}")
    return failed
