#!/bin/bash
# Start N gemma4 vllm instances on ports 8300..8300+N-1. Usage: ./start-gemma.sh [N=8] [TIME=10:00:00]
cd /scratch/user/$USER/fbbench-models
N=${1:-8}; T=${2:-10:00:00}
for p in $(seq 8300 $((8300+N-1))); do sbatch --time=$T --export=ALL,PORT=$p serve-vllm.slurm; done
