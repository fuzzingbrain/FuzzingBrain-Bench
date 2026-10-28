# Serving open-weight models on an HPC cluster (TAMU HPRC Grace/FASTER)

These are the scripts behind the "Serving open-weight models on an HPC cluster"
section of the top-level README. They serve an open-weight model (Qwen GGUF via
llama.cpp, or Gemma via vLLM) as OpenAI-compatible endpoints on the cluster's
GPU nodes, tunnel those endpoints to the machine that runs `fb-bench`, and let
the **api arm** drive the model (`--model qwen3.8:27b-q4`, keyless, `$0`).

```
cluster/   run on the cluster (Apptainer/Singularity + Slurm)
runner/    run on the machine that has fb-bench (needs SSH access to the cluster)
```

## Before you start — fill these in

- `YOUR_SLURM_ACCOUNT` in the `*.slurm` files → your Slurm `--account`.
- `HPRC_USER` / `CLUSTER` env for the `runner/` scripts → your NetID and cluster
  (`grace` or `faster`). Example: `export HPRC_USER=abc123 CLUSTER=grace`.
- Put a Hugging Face token in `~/.hf_token` on the cluster if a model needs one.
- The scripts assume the layout `/scratch/user/$USER/fbbench-models/` with
  `llama.sif`, `vllm.sif`, `logs/`, and the downloaded weights under `hf/`.

## 1. One-time (on the cluster)

```bash
# two SIF images, ~10 GB (pin a real tag)
apptainer pull vllm.sif  docker://vllm/vllm-openai:<tag>
apptainer pull llama.sif docker://ghcr.io/ggml-org/llama.cpp:server-cuda-<tag>
sbatch cluster/download-models.slurm qwen      # or: gemma / all
```

## 2. Serve N instances (on the cluster)

```bash
cd /scratch/user/$USER/fbbench-models
./start-qwen.sh 11          # 11 Qwen GGUF servers, ports 8000..8010 (1 A100 each)
./status.sh                 # job / node / port / READY|loading
```

## 3. Tunnel the endpoints (on the runner machine)

```bash
export HPRC_USER=your_netid CLUSTER=grace
bash runner/master.sh                                  # once: password + 2FA
./runner/tunnels-from-squeue.sh gguf-serve serve-gguf  # prints the env line below
#  -> export FBBENCH_AGENT_ENDPOINTS=http://localhost:8000/v1,...,http://localhost:8010/v1
```

## 4. Run the benchmark (on the runner machine)

```bash
export FBBENCH_AGENT_ENDPOINTS=http://localhost:8000/v1,...   # from step 3
fb-bench run all --arm api --model qwen3.8:27b-q4 \
    --max-turns 10000 --timeout 3600 --jobs 11 --output qwen-fb
```

Stop the servers when done — idle GPUs still burn allocation:

```bash
./stop.sh        # on the cluster
```

## Notes

- Each cell claims one endpoint from `FBBENCH_AGENT_ENDPOINTS` for its whole
  episode (waiting if there are fewer endpoints than `--jobs`), so set `--jobs`
  to the number of servers.
- The model id must match the server's advertised name: llama.cpp `--alias`
  (`qwen3.8:27b-q4`) or vLLM `--served-model-name` (`gemma4:31b-qat`). The `:` in
  the id routes it to the keyless local path.
- `tunnel-up.sh` / `tunnel-down.sh` add or remove a single forward by hand; the
  FASTER cluster uses the same scripts with `CLUSTER=faster`.
