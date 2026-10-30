#!/bin/sh
# Mounted over the debuggers (gdb, jdb, jdb-run) for a run started with
# --no-debugging-tool (see fbbench/sandbox.py).
echo "$(basename "$0") is not available in this benchmark configuration." >&2
exit 127
