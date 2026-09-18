# Agent tools

Tools the **agent arms** get and the bare `api` arm does not — claudecode, codex
and any external agent. That asymmetry is the point of v2: the v1 benchmark was
sealed and offline, so an agent could use only what its challenge image
happened to ship, and `gdb` is in 45 of the 78 images and absent from 33 for no
reason anybody chose.

## Where the binaries come from

A **pinned image**, not a directory somebody fills in:

```
tools image  ──►  cache on this host  ──►  bind-mounted file by file
(pinned)          (derived, disposable)     into /usr/local/bin
```

```bash
export FBBENCH_AGENT_TOOLS_IMAGE=ghcr.io/…/fbbench-agent-tools@sha256:…
```

Pull one image and every machine has identical bits. That is the whole reason
it is an image: a gitignored `bin/` means a second machine silently runs a
different benchmark, and the numbers stop being comparable — which is the only
thing a benchmark is for.

The challenge images are never modified. The cache lives in
`~/.cache/fbbench/agent-tools/<image-id>/` and is disposable; delete it and it
repopulates. Keyed by image id, so bumping the version repopulates rather than
reusing stale binaries.

Unset the variable and the mechanism is off: agents get whatever the challenge
image ships, exactly v1 behaviour, and a fresh clone runs with no download.

## Building the tools image

```dockerfile
FROM debian:bookworm-slim AS build
# …build statically linked binaries…
FROM scratch
COPY --from=build /out/gdb /tools/bin/gdb
```

Anything executable under `/tools/bin` becomes available. Publish it, pin it by
digest, and record that digest wherever you record the benchmark version.

## Rules for what goes in

- **Static only.** The gdb the challenge images ship is 10 MB against 59 shared
  libraries; copied into an image that lacks it, it will not start. `file` must
  say "statically linked".
- **Nothing that reads the answer.** These run inside the challenge container,
  next to `/opt/fbbench/oracle`. A tool is for observing the target, not for
  discovering what the planted bug is.
- **Nothing that fuzzes.** The ban is enforced on `exec` commands in
  `mcp_episode.py`; a tool that drives a fuzzer walks straight around it.
- **Reserved names** (`mcp-server`, `llvm-symbolizer`, `sh`, `bash`, `env`) are
  skipped — shadowing one breaks the episode in a way that looks like the
  agent's fault, which is also why these are mounted file by file and never as
  a directory.

## What a result records

`score.json` carries `agent_tools`, `agent_tools_image` and
`agent_tools_digest` per cell, so a number can be read knowing exactly what was
on `PATH` when it was produced — and two runs that disagree can be told apart.
