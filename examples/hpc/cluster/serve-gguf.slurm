#!/bin/bash
#SBATCH --job-name=gguf-serve
#SBATCH --partition=gpu
#SBATCH --account=YOUR_SLURM_ACCOUNT
#SBATCH --gres=gpu:a100:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=01:30:00
#SBATCH --output=logs/serve-gguf.%j.log
# One llama.cpp server (GGUF) on one GPU. Port from $PORT. Model id = --alias.
cd /scratch/user/$USER/fbbench-models
export XDG_CACHE_HOME=/scratch/user/$USER/fbbench-models/xdg-cache
export CUDA_CACHE_PATH=/scratch/user/$USER/fbbench-models/cuda-cache CUDA_CACHE_MAXSIZE=4294967296
GGUF=/scratch/user/$USER/fbbench-models/hf/hub/models--unsloth--Qwen3.8-27B-GGUF/snapshots/4ca720788d1e01f1bff70c033e0d0028fd02e502/Qwen3.8-27B-UD-Q4_K_M.gguf
echo "running on node: $(hostname)"
echo "model: $GGUF"
singularity exec --nv --bind /scratch/user/$USER llama.sif \
  sh -c 'export LD_LIBRARY_PATH=/app:$LD_LIBRARY_PATH; exec /app/llama-server "$@"' llama-server \
  -m "$GGUF" --alias qwen3.8:27b-q4 \
  --host 0.0.0.0 --port ${PORT:-8000} \
  -ngl 999 -c 262144 --parallel 1 -ctk q8_0 -ctv q8_0 \
  --jinja --reasoning-format deepseek --flash-attn on
