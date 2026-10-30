#!/bin/bash
# Print "port node job health" for running model instances (gguf-serve / gemma-serve).
cd /scratch/user/$USER/fbbench-models
for j in $(squeue -u $USER -h -n gguf-serve,gemma-serve -t RUNNING -o %i); do
  log=$(ls logs/*gguf.$j.log logs/*gemma.$j.log 2>/dev/null | head -1); [ -z "$log" ] && continue
  node=$(grep -m1 -oP 'running on node: \K\S+' "$log"); port=$(sacct -j $j -X -n -o SubmitLine%200 -P | grep -oP 'PORT=\K[0-9]+' | head -1)
  [ -z "$node" ] && { echo "$port ? $j loading"; continue; }
  code=$(curl -s --max-time 3 -o /dev/null -w '%{http_code}' http://$node:$port/health 2>/dev/null)
  echo "$port $node $j ${code:-000}"
done | sort
