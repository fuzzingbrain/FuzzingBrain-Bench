#!/bin/bash
#SBATCH --job-name=gemma-serve
#SBATCH --account=YOUR_SLURM_ACCOUNT
#SBATCH --partition=gpu
#SBATCH --gres=gpu:a100:1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=01:30:00
#SBATCH --output=logs/serve-gemma.%j.log
# One vLLM server on one GPU. Port from $PORT. --served-model-name is the model id.
cd /scratch/user/$USER/fbbench-models
export HF_HOME=/scratch/user/$USER/fbbench-models/hf HF_HUB_OFFLINE=1
export VLLM_CACHE_ROOT=/scratch/user/$USER/fbbench-models/vllm-cache
export TRITON_CACHE_DIR=/scratch/user/$USER/fbbench-models/triton-cache
export XDG_CACHE_HOME=/scratch/user/$USER/fbbench-models/xdg-cache
export CUDA_CACHE_PATH=/scratch/user/$USER/fbbench-models/cuda-cache
echo "running on node: $(hostname)"
singularity exec --nv --bind /scratch/user/$USER vllm.sif \
  vllm serve google/gemma-4-31B-it-qat-w4a16-ct \
    --revision 52f3f65bc7a02d555763bc923bd1d9094898219d \
    --served-model-name gemma4:31b-qat gemma4-test \
    --max-model-len 141760 --gpu-memory-utilization 0.95 --port ${PORT:-8000} \
    --reasoning-parser gemma4 --enable-auto-tool-choice --tool-call-parser gemma4 \
    --limit-mm-per-prompt '{"image":0,"video":0}'
