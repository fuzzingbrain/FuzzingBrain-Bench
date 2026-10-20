#!/bin/sh
# Mounted over gdb for a run started with --no-gdb (see fbbench/sandbox.py).
echo "gdb is not available in this benchmark configuration." >&2
exit 127
