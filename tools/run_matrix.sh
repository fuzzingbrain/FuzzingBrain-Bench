cd /data4/ze/FuzzingBrain-Bench
export PYTHONPATH=.:tools
run() { echo "===== $* @ $(date +%H:%M) ====="; "$@"; }
for MT in "claude-haiku-4-5 1500" "claude-sonnet-4-6 2400"; do
  set -- $MT; M=$1; TO=$2
  echo "########## MODEL $M ##########"
  run python3 tools/fullscan_batch.py --model $M --mode full-scan --concurrency 6 --max-turns 50 --episode-timeout $TO
  run python3 tools/fullscan_batch.py --model $M --mode normal    --concurrency 6 --max-turns 50 --episode-timeout $TO
  for L in 0 1 2 3; do
    run python3 tools/diffscan_batch.py --model $M --diff-level $L --concurrency 6 --max-turns 50 --episode-timeout $TO
  done
done
echo "########## MATRIX DONE @ $(date +%H:%M) ##########"
