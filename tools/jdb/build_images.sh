#!/usr/bin/env bash
# Add jdb to the JVM agent images: a thin layer per challenge over the published
# image (see Dockerfile here). One build at a time.
#
#   tools/jdb/build_images.sh [-p PREFIX] [--base PFX] [--push] [alias ...]
#
#   -p PREFIX     image prefix to tag; default docker.io/osanzas/fbbench-agent-
#                 Use a local prefix (e.g. local/fbbench-agent-) to test without
#                 touching the published tags:
#                 FBBENCH_AGENT_IMAGE_PREFIX=local/fbbench-agent- fb-bench run ...
#   --base PFX    the images to layer on (default docker.io/osanzas/fbbench-agent-)
#   --push        docker push each tag after building
#   alias ...     challenges to build; default: every bugs/*/*/bench.yaml with engine jazzer
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../.." && pwd)
PREFIX=docker.io/osanzas/fbbench-agent-
BASE_PREFIX=docker.io/osanzas/fbbench-agent-
PUSH=0
ALIASES=()
while [ $# -gt 0 ]; do
  case "$1" in
    -p) PREFIX=$2; shift 2;;
    --base) BASE_PREFIX=$2; shift 2;;
    --push) PUSH=1; shift;;
    -h|--help) sed -n '2,14p' "$0"; exit 0;;
    *) ALIASES+=("$1"); shift;;
  esac
done
if [ ${#ALIASES[@]} -eq 0 ]; then
  for f in "$ROOT"/bugs/*/*/bench.yaml; do
    grep -q 'engine: *jazzer' "$f" && ALIASES+=("$(basename "$(dirname "$f")")")
  done
fi

ok=0; fail=()
for a in "${ALIASES[@]}"; do
  base="${BASE_PREFIX}${a}:latest"
  tag="${PREFIX}${a}:latest"
  ver=$(docker run --rm --entrypoint dpkg-query "$base" -W -f='${Version}' openjdk-17-jre-headless 2>/dev/null || true)
  if [ -z "$ver" ]; then echo "SKIP $a: no openjdk-17-jre-headless in $base"; fail+=("$a"); continue; fi
  echo "== $a  ($base -> $tag, JDK $ver)"
  if ! docker build -q -f "$HERE/Dockerfile" --build-arg BASE="$base" --build-arg JDK_VERSION="$ver" \
       -t "$tag" "$HERE" >/dev/null; then
    echo "FAIL $a: build"; fail+=("$a"); continue
  fi
  # the layer is honest only if the JRE that runs the harness did not move
  # and the driver answers in the image as shipped
  after=$(docker run --rm --entrypoint dpkg-query "$tag" -W -f='${Version}' openjdk-17-jre-headless)
  if [ "$after" != "$ver" ] || ! docker run --rm --network none --entrypoint jdb-run "$tag" --help >/dev/null 2>&1; then
    echo "FAIL $a: JRE moved ($ver -> $after) or jdb-run broken"; fail+=("$a"); continue
  fi
  echo "   sourcepath: $(docker run --rm --entrypoint sh "$tag" -c 'tr : "\n" < /opt/fbbench-jdb/sourcepath | wc -l') roots"
  ok=$((ok+1))
  if [ "$PUSH" = 1 ]; then docker push -q "$tag"; fi
done
echo "built $ok of ${#ALIASES[@]}${fail:+; failed: ${fail[*]}}"
[ ${#fail[@]} -eq 0 ]
