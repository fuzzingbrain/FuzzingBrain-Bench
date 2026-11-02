#!/usr/bin/env bash
# Run all 77 challenges with D+G, followed by all 77 with neither tool.
set -euo pipefail

OUT=${1:-output/flash-next-77x2}
BASE_URL=${FLASHNEXT_BASE_URL:-http://localhost:8000/v1}
MODEL=qwen3.8-flash-next:fp8
JOBS=${FLASHNEXT_JOBS:-11}

curl --silent --show-error --fail "$BASE_URL/models" | grep -q "\"$MODEL\""
mkdir -p "$OUT"

# Repeating the one URL creates eleven endpoint-pool slots. All slots share the
# same continuously-batched vLLM server.
endpoints=()
for ((i=0; i<JOBS; i++)); do endpoints+=("$BASE_URL"); done
export FBBENCH_AGENT_ENDPOINTS
FBBENCH_AGENT_ENDPOINTS=$(IFS=,; echo "${endpoints[*]}")

COMMON=(
  --arm api
  --model "$MODEL"
  --max-turns 10000
  --timeout 3600
  --jobs "$JOBS"
  --preserve-pocs
  --no-stop-on-crash
  --no-dashboard
)

git log -1 --format='code: %H %s' >"$OUT/code-version.txt"
git diff --stat >>"$OUT/code-version.txt"

echo "== D+G start $(date -Is)" | tee -a "$OUT/run.log"
fb-bench run all "${COMMON[@]}" --output "$OUT/flash-next-dg" 2>&1 | tee -a "$OUT/run.log"

echo "== no-D/G start $(date -Is)" | tee -a "$OUT/run.log"
fb-bench run all "${COMMON[@]}" \
  --no-debugging-tool --no-callgraph \
  --output "$OUT/flash-next-nodg" 2>&1 | tee -a "$OUT/run.log"

echo "== complete $(date -Is)" | tee -a "$OUT/run.log"
