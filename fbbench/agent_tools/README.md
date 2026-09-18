# Agent tools

Executables dropped in `bin/` are bind-mounted read-only into `/usr/local/bin`
inside the challenge image, for **agent arms only** — claudecode, codex and any
external agent. The bare `api` arm starts its own container through
`fbbench/runner/mcp_client.py` and never sees them.

That asymmetry is the point of v2. The v1 benchmark was sealed and offline: an
agent could use only what the image already shipped, and `gdb` happens to be in
45 of the 78 challenge images and absent from the other 33, for no reason
anybody chose. Agent arms get a consistent set instead.

## Adding one

Drop a **statically linked** executable in `bin/` and make it executable. That
is the whole procedure — it appears on `PATH` in every challenge, and an agent
reaches it through `exec` like any other command. No MCP tool to declare, no
wrapper to keep in sync.

`score.json` records `agent_tools` per cell, so a result can be read knowing
what was available when it was produced.

## Rules

- **Static only.** The gdb the images ship is 10 MB against 59 shared
  libraries; copied into an image that lacks it, it will not start. Check with
  `file` — it must say "statically linked".
- **Nothing that reads the answer.** These run inside the challenge container
  next to `/opt/fbbench/oracle`. A tool is for observing the target, not for
  finding out what the planted bug is.
- **Nothing that fuzzes.** The ban is enforced on `exec` commands in
  `mcp_episode.py`; a tool that drives a fuzzer would walk straight around it.
- **Reserved names** (`mcp-server`, `llvm-symbolizer`, `sh`, `bash`, `env`) are
  skipped: shadowing one breaks the episode in a way that looks like the
  agent's fault.

## Where the binaries live

`bin/` is gitignored by default — these are tens of megabytes each and do not
belong in a clone. Point `FBBENCH_AGENT_TOOLS` at a directory elsewhere if you
would rather keep them outside the tree entirely.

An empty or missing directory is fine: agents then have whatever the image
itself ships, which is exactly the v1 behaviour.
