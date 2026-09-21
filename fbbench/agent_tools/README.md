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

Nobody sets anything. The first time an agent episode starts on a machine, the
benchmark pulls the published toolbox image and caches it — ~11MB, once. gdb is
part of the benchmark, not a dependency somebody installs and not a flag
somebody has to know about.

```bash
# only if you are pinning a digest or using your own registry
export FBBENCH_AGENT_TOOLS_IMAGE=ghcr.io/…/fbbench-agent-tools@sha256:…
# deliberate opt-out: agent arms then get only what the image ships
export FBBENCH_AGENT_TOOLS_IMAGE=none
```

If that pull fails, the run **stops**. It does not quietly continue without
gdb: an agent arm missing its debugger still produces a number, and that number
is not comparable to one produced with it — on 33 of the 78 challenges it would
mean no debugger at all, with nothing in the output saying so.

Pull one image and every machine has identical bits. That is the whole reason
it is an image: a gitignored `bin/` means a second machine silently runs a
different benchmark, and the numbers stop being comparable — which is the only
thing a benchmark is for.

The challenge images are never modified. The cache lives in
`~/.cache/fbbench/agent-tools/<image-id>/` and is disposable; delete it and it
repopulates. Keyed by image id, so bumping the version repopulates rather than
reusing stale binaries.

Set the variable to `none` and the mechanism is off: agents get whatever the
challenge image ships, exactly v1 behaviour. That is the only way to end up
without it, and it has to be chosen.

## Building the tools image

`Dockerfile` beside this file builds it. One command, no arguments, and it
refuses to produce anything that would not run everywhere:

```bash
docker build -t <registry>/fbbench-agent-tools:v1 fbbench/agent_tools/
docker push  <registry>/fbbench-agent-tools:v1
export FBBENCH_AGENT_TOOLS_IMAGE=<registry>/fbbench-agent-tools@sha256:…
```

Currently one tool: **gdb 14.2, statically linked, 10.4 MB, no dynamic loader.**
Verified to start and set source-level breakpoints inside `skia-01` and
`libxml2-04`, two challenge images that ship no debugger at all.

Two things about that build are worth knowing before changing it.

**It is built on Alpine, not Debian.** Alpine's C library (musl) is designed to
be baked into a program; Debian's (glibc) is not, and parts of it load more
pieces at runtime no matter what you ask for. Seven Debian attempts shed expat,
gmp and mpfr and still could not shake libc, libm and libstdc++. A musl-built
gdb debugging a glibc-built harness is fine — gdb inspects the target from the
outside and shares nothing with it.

**gdb links itself through libtool, not through the compiler**, and to libtool
`-static` means "prefer static archives when resolving `-l` flags", not
"produce a self-contained executable". libtool consumes the flag instead of
passing it on. Five builds oscillated — musl libc dynamic, then libstdc++
dynamic, then musl again — because the flag was being addressed to the wrong
program. The flag libtool understands is `-all-static`, and it belongs on the
final link only: `configure` link-tests with the compiler directly and would
reject an option gcc does not have.

The build ends by reading gdb's own ELF headers and **failing** if a dynamic
loader is named there. Note that `ldd` cannot answer this on Alpine — `ldd`
*is* the musl loader and prints a `libc.musl-x86_64.so.1 => …` line even for a
fully static binary. Four good builds were thrown away on that false positive
before `readelf -l` settled it. A dynamic executable carries an `INTERP`
program header; a static one has none.

Anything executable under `/tools/bin` becomes available. The image is `FROM
scratch` — binaries and nothing else, no shell — so the benchmark extracts them
with `docker create` + `docker cp` rather than running anything inside it.

## Rules for what goes in

- **Static only.** The gdb the challenge images ship is 10 MB against 59 shared
  libraries; copied into an image that lacks it, it will not start.
  `readelf -l` must show no `INTERP` header — and `tests/test_agent_tools.py`
  checks every binary in a built image, so a dynamic one cannot slip through.
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
