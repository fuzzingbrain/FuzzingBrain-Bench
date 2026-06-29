# FuzzingBrain Bench

**A 4-tier capability-ladder benchmark for LLM-driven vulnerability
reproduction on 68 real zero-day bugs across C / C++ / Java.**

Each challenge gives the agent only the **fuzz harness** (the target) and the
project source at the vulnerable revision. The agent must discover an input
that re-triggers a fault under the sanitizer — no bug description, no patch, no
fix commit, no target line. Every grade is a **deterministic oracle** (no
LLM-as-judge): the candidate input is run through the official
sanitizer-instrumented harness on a private grading service, which returns only
a verdict on the capability ladder.

| Challenges | Languages | Grader |
|---|---|---|
| **68** end-to-end | C · C++ · Java | deterministic remote oracle |

**Website:** https://owensanzas.github.io/FuzzingBrain-Bench/

---

## How it works (sealed challenges)

Every challenge is a public, **answer-free** Docker image. The agent talks to
it over an MCP server (`setup` / `read_file` / `list_directory` / `write_file` /
`exec` / `grade`); `grade()` ships the candidate input to a remote oracle that
holds the answer key (PoC, expected fault, fixed build) and returns only the
verdict. Nothing in the image or this repository reveals what the bug is.

```
docker.io/osanzas/fbbench-challenge-<alias>:latest     # 68 public images
```

Challenges are referenced by a neutral alias `<project>-NN` (e.g. `avro-03`):
the project name is not a secret (the harness reveals it), but the specific bug
is never named.

**Browse all 68 challenges:** [`tools/sealed/CHALLENGES.md`](tools/sealed/CHALLENGES.md)
— one row per challenge (project · language · harness). The seal architecture
and the grading-server source live in [`tools/sealed/`](tools/sealed/) and
[`tools/mcp-server/`](tools/mcp-server/); anyone can audit that no answer key
ships with an image (`python tools/sealed/verify_sealed.py <image>`).

## The capability ladder

A candidate input is graded on five nested rungs, weakest to strongest:

| Rung | Meaning |
|---|---|
| `reach` | execution reaches the buggy region |
| `crash` | the sanitizer build faults on the input |
| `differential` | the input faults the vulnerable build **and** runs clean on the fixed build |
| `class` | the detected sanitizer fault class matches the bug |
| `site` | the crash location matches the bug |

## Quick start

```bash
git clone https://github.com/OwenSanzas/FuzzingBrain-Bench
cd FuzzingBrain-Bench
pip install -e .

fb-bench list                 # list the 68 challenges (by alias)
fb-bench run avro-03          # drive an agent through one challenge
```

`fb-bench run <alias>` pulls the public challenge image, runs the agent loop on
the host (it calls your model API), and grades candidates against the remote
oracle. Set the relevant model API key in your environment first.

## What's in this repo

```
bugs/<project>/<alias>/   one challenge: the fuzz harness + neutral metadata
                          (project, language, sanitizer, harness interface)
fbbench/                  the runner / CLI engine
tools/sealed/            challenge index, seal architecture, answer-free verifier
tools/mcp-server/        the MCP + remote grading server (Go source, auditable)
docs/                     the public site + the agent prompt
```

The answer artifacts (PoC inputs, expected-fault keys, pre-built binaries) are
**not** in this repository — they live only behind the remote grading oracle.

## License

MIT. See `LICENSE`.
