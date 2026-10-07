#!/usr/bin/env bash
# Rebuild the agent images with the static call graph: a thin layer per
# challenge over the published image (see Dockerfile here).
#
#   tools/callgraph/build_images.sh [-g GRAPH_DIR] [-p PREFIX] [--push] [alias ...]
#
#   -g GRAPH_DIR  where <alias>.callgraph.sqlite live
#                 (default /home/ze/fbbench-output/callgraphs; see build_sqlite.py)
#   -p PREFIX     image prefix to tag; default docker.io/osanzas/fbbench-agent-
#                 Use a local prefix (e.g. local/fbbench-agent-) to test one
#                 challenge without touching the published tags:
#                 FBBENCH_AGENT_IMAGE_PREFIX=local/fbbench-agent- fb-bench run ...
#   --base PFX    the images to layer on (default: same as -p, i.e. the published ones)
#   --push        docker push each tag after building
#   alias ...     challenges to build; default: every <alias>.callgraph.sqlite in GRAPH_DIR
#
# The mcp-server is built once, statically (CGO_ENABLED=0), from tools/mcp-server.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
GRAPH_DIR=/home/ze/fbbench-output/callgraphs
PREFIX=docker.io/osanzas/fbbench-agent-
BASE_PREFIX=""
PUSH=0
ALIASES=()
while [ $# -gt 0 ]; do
  case "$1" in
    -g) GRAPH_DIR=$2; shift 2;;
    -p) PREFIX=$2; shift 2;;
    --base) BASE_PREFIX=$2; shift 2;;
    --push) PUSH=1; shift;;
    -h|--help) sed -n '2,20p' "$0"; exit 0;;
    *) ALIASES+=("$1"); shift;;
  esac
done
BASE_PREFIX=${BASE_PREFIX:-docker.io/osanzas/fbbench-agent-}
if [ ${#ALIASES[@]} -eq 0 ]; then
  for f in "$GRAPH_DIR"/*.callgraph.sqlite; do
    b=$(basename "$f"); ALIASES+=("${b%.callgraph.sqlite}")
  done
fi

CTX=$(mktemp -d /tmp/fbbench-cg-ctx.XXXXXX)
trap 'rm -rf "$CTX"' EXIT
echo "building mcp-server (static) ..."
(cd "$ROOT/tools/mcp-server" && GOTOOLCHAIN=local CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o "$CTX/mcp-server" .)
cp "$HERE/Dockerfile" "$CTX/Dockerfile"

ok=0; fail=()
for a in "${ALIASES[@]}"; do
  g="$GRAPH_DIR/$a.callgraph.sqlite"
  if [ ! -f "$g" ]; then echo "SKIP $a: no $g"; fail+=("$a"); continue; fi
  cp "$g" "$CTX/$a.callgraph.sqlite"
  tag="${PREFIX}${a}:latest"
  base="${BASE_PREFIX}${a}:latest"
  echo "== $a  ($base -> $tag)"
  if docker build -q -f "$CTX/Dockerfile" --build-arg BASE="$base" --build-arg GRAPH="$a.callgraph.sqlite" -t "$tag" "$CTX" >/dev/null; then
    # the layer is honest only if the server inside answers from the shipped file
    if docker run --rm --entrypoint cg "$tag" info >/dev/null 2>&1; then
      ok=$((ok+1))
      [ $PUSH = 1 ] && docker push -q "$tag"
    else
      echo "FAIL $a: cg info does not answer inside the image"; fail+=("$a")
    fi
  else
    echo "FAIL $a: docker build"; fail+=("$a")
  fi
  rm -f "$CTX/$a.callgraph.sqlite"
done
echo "built $ok / ${#ALIASES[@]}"
[ ${#fail[@]} -eq 0 ] || { echo "failed: ${fail[*]}"; exit 1; }
