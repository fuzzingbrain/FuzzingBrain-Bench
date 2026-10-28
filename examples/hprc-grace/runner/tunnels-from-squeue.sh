#!/usr/bin/env bash
# Step 2: forward every READY serve instance's port to the same local port, and print
# the FBBENCH_AGENT_ENDPOINTS line. Nodes come from squeue, ports from the startup logs.
#   qwen:  CLUSTER=grace HPRC_USER=you ./tunnels-from-squeue.sh gguf-serve  serve-gguf
#   gemma: CLUSTER=grace HPRC_USER=you ./tunnels-from-squeue.sh gemma-serve serve-gemma
set -uo pipefail
CLUSTER="${CLUSTER:-grace}"; U="${HPRC_USER:-YOUR_NETID}"
S=~/.ssh/cm/${CLUSTER}.sock; H="${U}@${CLUSTER}.hprc.tamu.edu"
JOB="${1:-gemma-serve}"; LOG="${2:-serve-gemma}"
D="${MODEL_LOGS:-/scratch/user/$U/fbbench-models/logs}"
ssh -S "$S" -O check "$H" 2>/dev/null || { echo "master not up; run master.sh first"; exit 1; }
rows=$(ssh -S "$S" "$H" "for j in \$(squeue -u $U -n $JOB -t RUNNING -h -o '%i:%N'); do
  id=\${j%%:*}; node=\${j##*:}; f=$D/$LOG.\$id.log
  grep -qE 'Application startup complete|listening on http' \$f 2>/dev/null || continue
  port=\$(grep -oE \"'port': [0-9]+|listening on http://[0-9.]+:[0-9]+\" \$f | head -1 | grep -oE '[0-9]+\$')
  echo \$node \${port:-8000}
done" 2>/dev/null | grep -E '^[a-z0-9-]+ [0-9]+$')
[ -z "$rows" ] && { echo "no READY $JOB instances"; exit 1; }
eps=()
while read -r node port; do
  ssh -S "$S" -O forward -L "${port}:${node}:${port}" "$H" 2>/dev/null
  if curl -s -m 10 "localhost:${port}/v1/models" | grep -q '"id"'; then
    echo "OK   localhost:${port} -> ${node}:${port}"; eps+=("http://localhost:${port}/v1")
  else echo "FAIL localhost:${port} -> ${node}:${port}"; fi
done <<< "$rows"
echo; echo "export FBBENCH_AGENT_ENDPOINTS=$(IFS=,; echo "${eps[*]}")"
