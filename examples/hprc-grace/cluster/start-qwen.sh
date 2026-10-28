#!/bin/bash
# Start N qwen3.8 llama-server instances on ports 8000..8000+N-1. Usage: ./start-qwen.sh [N=8] [TIME=15:00:00]
cd /scratch/user/$USER/fbbench-models
N=${1:-8}; T=${2:-15:00:00}
for p in $(seq 8000 $((8000+N-1))); do sbatch --time=$T --export=ALL,PORT=$p serve-gguf.slurm; done
