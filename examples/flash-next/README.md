# Reproducing the Qwen3.8-Flash-Next experiment

This directory records the complete serving and benchmark configuration used
for the 77-challenge Qwen3.8-Flash-Next evaluation on 31 October--1 November
2026. Site-specific account names, usernames, and storage paths are parameters;
the model and inference flags are the flags used in the experiment.

## Hardware and software

The model server used one exclusive NCSA DeltaAI `ghx4` node:

- four NVIDIA Grace-Hopper GH200 superchips;
- four NVIDIA H100 GPUs, each reporting 97,871 MiB of usable memory;
- four 72-core Grace CPUs and 480 GB LPDDR5 CPU memory; and
- 384 GB total HBM3 GPU memory.

The server was vLLM `0.33.0rc1.dev320+g335dd77b0` in an Apptainer image with
digest:

```
sha256:66f19872e759e7d74f0729c4c7068eaaf71bc8b35f613573c36062a81be8cb3d
```

The downloaded `Qwen/Qwen3.8-Flash-Next-FP8` weights were at Hugging Face
revision `236dfdf285828023ca3bcd3f37366c58a3469b13`. The experiment used the
text-only language model. The model checkpoint occupied 172.78 GiB and loaded
as FP8.

The challenge containers and API-arm controller ran on a separate x86-64
machine. Eleven challenges ran concurrently and shared the single vLLM
endpoint.

## Server parameters

[`cluster/serve-flash-next.slurm`](cluster/serve-flash-next.slurm) is the
sanitized version of the job script used in the experiment. Its important
settings are:

| Setting | Value |
|---|---|
| Model precision | FP8 |
| Tensor parallel size | 4 |
| Expert parallelism | enabled, Triton MoE backend |
| Context window | 262,144 tokens |
| GPU memory utilization | 0.85 |
| KV cache | FP8 |
| Sparse-attention indexer KV | FP8 |
| Maximum sequences | 256 |
| Prefix caching | enabled |
| Speculative decoding | MTP, 3 speculative tokens |
| Tool parser | `qwen3_coder` |
| Reasoning parser | `qwen3` |
| Serving mode | language model only |

The effective vLLM configuration also enabled chunked prefill with 8,192
maximum batched tokens. The server resolved the primary architecture as
`Qwen4ExpForConditionalGeneration`, used FlashAttention 3, and used a TP and EP
world size of four.

Before submitting the job, place the model at
`$FLASHNEXT_ROOT/hf/Qwen3.8-Flash-Next-FP8` and the pinned Apptainer image at
`$FLASHNEXT_ROOT/sif/vllm-nightly.sif`. Then run:

```bash
export FLASHNEXT_ACCOUNT=your-deltaai-account
export FLASHNEXT_ROOT=/work/nvme/your-project/$USER/flash-next
mkdir -p "$FLASHNEXT_ROOT"/{hf,sif,cache,logs}
hf download Qwen/Qwen3.8-Flash-Next-FP8 \
  --revision 236dfdf285828023ca3bcd3f37366c58a3469b13 \
  --local-dir "$FLASHNEXT_ROOT/hf/Qwen3.8-Flash-Next-FP8"
sbatch --account="$FLASHNEXT_ACCOUNT" \
  --output="$FLASHNEXT_ROOT/logs/serve-%j.log" \
  examples/flash-next/cluster/serve-flash-next.slurm
```

The job log prints the compute node and port. Wait until `/v1/models` responds
before starting the benchmark.

## Tunnel and endpoint validation

Open the persistent SSH connection from the benchmark machine:

```bash
export DTAI_USER=your-ncsa-user
bash examples/flash-next/runner/master.sh
```

Forward local port 8000 to the node reported by Slurm:

```bash
ssh -S ~/.ssh/cm/deltaai.sock -O forward \
  -L 8000:COMPUTE_NODE:8000 \
  "$DTAI_USER@dtai-login.delta.ncsa.illinois.edu"
curl --fail http://localhost:8000/v1/models
```

Run [`runner/smoke.sh`](runner/smoke.sh) before an expensive sweep. It verifies
the model id and native tool-call parsing.

## Formal benchmark parameters

[`runner/run-77x2.sh`](runner/run-77x2.sh) reproduces the two formal sweeps:

1. all 77 challenges with the debugger and static call graph (D+G); and
2. all 77 challenges with both tools disabled.

Both sweeps used:

- `--arm api`;
- model id `qwen3.8-flash-next:fp8`;
- temperature 1.0, top-p 0.95, and top-k 20;
- 11 concurrent cells;
- a 3,600-second wall-clock limit per challenge;
- `--max-turns 10000`;
- continued discovery after a crash; and
- preservation of submitted PoCs.

Run from the repository root after the tunnel is ready:

```bash
bash examples/flash-next/runner/run-77x2.sh output/flash-next-77x2
```

The same endpoint is intentionally repeated eleven times in
`FBBENCH_AGENT_ENDPOINTS`: vLLM performs continuous batching for all workers.

## Response-speed collection

The API arm records `latency_s`, input/output token counts, and
`output_tok_per_s` for every model call. Each episode and sweep also contains
pooled latency statistics.

For independent server-side telemetry, run the Prometheus sampler alongside
the benchmark:

```bash
python3 examples/flash-next/vllm_metrics.py \
  http://localhost:8000 output/flash-next-77x2/vllm.csv 10
```

Across the final assembled experiment data, the measured per-request response
statistics were:

| Configuration | Calls | Median | P90 | Mean | Output tok/s |
|---|---:|---:|---:|---:|---:|
| D+G | 10,935 | 9.19 s | 40.04 s | 16.04 s | 176.63 |
| No D/G | 9,700 | 9.06 s | 38.40 s | 15.70 s | 184.19 |

The vLLM server metrics across the original and recovery phases recorded a
mean aggregate decode throughput of 1,625 output tokens/s, a median of 1,680
tokens/s, and a 10th--90th percentile interval of 1,270--1,959 tokens/s. These
aggregate figures cover all concurrently active requests and should not be
confused with per-request output speed.

## Interpretation of comparisons

This configuration supports an end-to-end comparison under the same
wall-clock budget. It is not a hardware-normalized model comparison with the
earlier Qwen3.8-27B deployment, which used Q4_K_M GGUF weights, llama.cpp, and
one A100 40 GB server per worker. Hardware, quantization, inference engine, and
serving topology all differ.
