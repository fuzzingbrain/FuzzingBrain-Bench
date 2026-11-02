#!/bin/bash
# Qwen3.8-Flash-Next-FP8 on one NCSA DeltaAI node (4x GH200).
# This contains the serving flags used by the experiment. Only account and
# storage paths have been parameterized.
#
#   FLASHNEXT_ACCOUNT=... FLASHNEXT_ROOT=... sbatch serve-flash-next.slurm
#SBATCH --job-name=flash-next
#SBATCH --partition=ghx4
#SBATCH --nodes=1
#SBATCH --gpus-per-node=4
#SBATCH --exclusive
#SBATCH --mem=0
#SBATCH --time=15:00:00
#SBATCH --output=logs/serve-%j.log

set -euo pipefail

: "${FLASHNEXT_ACCOUNT:?set FLASHNEXT_ACCOUNT to the DeltaAI Slurm account}"
: "${FLASHNEXT_ROOT:?set FLASHNEXT_ROOT to the flash-next storage directory}"

# Slurm does not expand an environment variable in an #SBATCH directive.
# Supply the account with `sbatch --account="$FLASHNEXT_ACCOUNT" ...` or set a
# default account in the site configuration.
PORT=${PORT:-8000}
MODEL_ID=qwen3.8-flash-next:fp8
MODEL_DIR=${MODEL_DIR:-$FLASHNEXT_ROOT/hf/Qwen3.8-Flash-Next-FP8}
VLLM_SIF=${VLLM_SIF:-$FLASHNEXT_ROOT/sif/vllm-nightly.sif}
CACHE_DIR=${CACHE_DIR:-$FLASHNEXT_ROOT/cache}

mkdir -p "$CACHE_DIR" logs
echo "job=$SLURM_JOB_ID node=$(hostname) port=$PORT start=$(date -Is)"
nvidia-smi --query-gpu=index,name,memory.total --format=csv

export APPTAINERENV_HF_HUB_OFFLINE=1
export APPTAINERENV_VLLM_CACHE_ROOT=/cache/vllm
export APPTAINERENV_TRITON_CACHE_DIR=/cache/triton
export APPTAINERENV_XDG_CACHE_HOME=/cache/xdg

apptainer exec --nv \
  --bind "$MODEL_DIR:/models/Qwen3.8-Flash-Next-FP8:ro" \
  --bind "$CACHE_DIR:/cache" \
  "$VLLM_SIF" \
  vllm serve /models/Qwen3.8-Flash-Next-FP8 \
    --served-model-name "$MODEL_ID" \
    --host 0.0.0.0 --port "$PORT" \
    --tensor-parallel-size 4 --enable-expert-parallel \
    --moe-backend triton \
    --gpu-memory-utilization 0.85 \
    --kv-cache-dtype fp8 --attention-config.indexer_kv_dtype fp8 \
    --max-model-len 262144 \
    --max-num-seqs 256 --enable-prefix-caching \
    --speculative-config '{"method":"mtp","num_speculative_tokens":3}' \
    --enable-auto-tool-choice --tool-call-parser qwen3_coder \
    --reasoning-parser qwen3 \
    --language-model-only
