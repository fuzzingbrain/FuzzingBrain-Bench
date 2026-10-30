# One thin layer on top of a published agent image: the static call graph and
# the mcp-server that serves it (as four MCP tools and as `cg` in the shell).
#
#   docker build -f tools/callgraph/Dockerfile \
#     --build-arg BASE=docker.io/osanzas/fbbench-agent-cups-01:latest \
#     --build-arg GRAPH=cups-01.callgraph.sqlite \
#     -t docker.io/osanzas/fbbench-agent-cups-01:latest  <context dir holding mcp-server + the .sqlite>
#
# Nothing else in the image changes: same source, same harness binary, same gdb,
# so a golden PoC produces the same signature as before. build_images.sh drives
# this for every challenge.
ARG BASE
FROM ${BASE}
ARG GRAPH
# plain COPY + chmod: the hosts that build these run the classic builder (no BuildKit)
COPY ${GRAPH} /challenge/callgraph.sqlite
COPY mcp-server /usr/local/bin/mcp-server
# `cg` is a wrapper script, not a symlink: --no-callgraph bind-mounts a stub over
# it, and a mount over a symlink would land on mcp-server itself.
RUN chmod 0644 /challenge/callgraph.sqlite && chmod 0755 /usr/local/bin/mcp-server \
 && printf '#!/bin/sh\nexec /usr/local/bin/mcp-server cg "$@"\n' > /usr/local/bin/cg \
 && chmod 0755 /usr/local/bin/cg
