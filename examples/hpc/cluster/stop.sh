#!/bin/bash
# Cancel all model-serving jobs (idle GPUs still burn allocation). Usage: ./stop.sh [gemma|qwen|all]
case ${1:-all} in
  gemma) scancel -u $USER -n gemma-serve ;;
  qwen)  scancel -u $USER -n gguf-serve ;;
  all)   scancel -u $USER -n gemma-serve; scancel -u $USER -n gguf-serve ;;
esac
squeue -u $USER
