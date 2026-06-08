#!/bin/bash
# Full experiment matrix: 6 cells (full-scan, normal, diff-0/1/2/3) x 2 models.
# Bug set is PINNED to the git-tracked corpus (untracked WIP bugs are excluded),
# so adding bugs on another branch can't contaminate this run. Resume-safe:
# every batch skips cells that already have a score.json.
cd /data4/ze/FuzzingBrain-Bench
export PYTHONPATH=.:tools

# Canonical 48: bugs tracked in git (excludes untracked in-progress dirs).
BUGS=$(git ls-files 'bugs/*/*/bench.yaml' | awk -F/ '{print $3}' | sort -u)
echo "pinned corpus: $(echo $BUGS | wc -w) bugs"

run() { echo "===== $* @ $(date +%H:%M) ====="; "$@"; }
for MT in "claude-haiku-4-5 1500" "claude-sonnet-4-6 2400"; do
  set -- $MT; M=$1; TO=$2
  echo "########## MODEL $M ##########"
  run python3 tools/fullscan_batch.py --model "$M" --mode full-scan --concurrency 6 --max-turns 50 --episode-timeout "$TO" --bugs $BUGS
  run python3 tools/fullscan_batch.py --model "$M" --mode normal    --concurrency 6 --max-turns 50 --episode-timeout "$TO" --bugs $BUGS
  for L in 0 1 2 3; do
    run python3 tools/diffscan_batch.py --model "$M" --diff-level $L --concurrency 6 --max-turns 50 --episode-timeout "$TO" --bugs $BUGS
  done
done
echo "########## MATRIX DONE @ $(date +%H:%M) ##########"
