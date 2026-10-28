#!/bin/bash
#SBATCH --job-name=hf-download
#SBATCH --account=YOUR_SLURM_ACCOUNT
#SBATCH --partition=short
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=02:00:00
#SBATCH --output=logs/download.%j.log
# Usage: sbatch download-models.slurm [gemma|qwen|all]   (default all)
set -euo pipefail
cd /scratch/user/$USER/fbbench-models
export HF_HOME=/scratch/user/$USER/fbbench-models/hf
export HF_HUB_OFFLINE=0
[ -s ~/.hf_token ] && export HF_TOKEN=$(cat ~/.hf_token)
WHAT=${1:-all}
echo "node: $(hostname)  start: $(date)  what: $WHAT"
dl() { singularity exec --bind /scratch/user/$USER vllm.sif hf download "$@"; }
if [ "$WHAT" = gemma ] || [ "$WHAT" = all ]; then
  echo "== gemma"; dl google/gemma-4-31B-it-qat-w4a16-ct --revision 52f3f65bc7a02d555763bc923bd1d9094898219d
fi
if [ "$WHAT" = qwen ] || [ "$WHAT" = all ]; then
  echo "== qwen";  dl unsloth/Qwen3.8-27B-GGUF Qwen3.8-27B-UD-Q4_K_M.gguf --revision 4ca720788d1e01f1bff70c033e0d0028fd02e502
fi
echo "done: $(date)"
