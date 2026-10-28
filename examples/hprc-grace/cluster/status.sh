#!/bin/bash
# Show model-serving jobs, which node/port each is on, and whether the API answers.
cd /scratch/user/$USER/fbbench-models
squeue -u $USER -o '%.10i %.12j %.9T %.10M %.10L %R' -n gemma-serve,gguf-serve,hf-download
echo
for j in $(squeue -u $USER -h -o '%i' -n gemma-serve,gguf-serve -t RUNNING); do
  log=$(ls logs/serve-*.$j.log 2>/dev/null | head -1); [ -z "$log" ] && continue
  node=$(grep -m1 -oP 'running on node: \K\S+' "$log")
  port=$(sacct -j $j -X -n -o SubmitLine%200 -P | grep -oP 'PORT=\K[0-9]+' | head -1)
  if curl -s --max-time 3 "http://$node:$port/v1/models" >/dev/null 2>&1; then st=READY; else st=loading; fi
  printf '%-10s %-6s %-6s %s\n' "$j" "$node" "$port" "$st"
done
