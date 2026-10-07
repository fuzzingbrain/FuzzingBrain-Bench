#!/bin/sh
# Mounted over /usr/local/bin/cg by `fb-bench run --no-callgraph` (sandbox.py):
# the ablation arm has no static call graph, in the shell as well as in the
# tool list. Mirrors gdb-unavailable.sh.
echo "cg: no call graph is available in this image" >&2
exit 1
