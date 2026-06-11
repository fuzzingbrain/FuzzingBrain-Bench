# FuzzingBrain Bench — Status

Snapshot of where the benchmark stands.

## Phases

| Phase | What | Status |
|-------|------|--------|
| 1 | SPEC + bug corpus | done — see [docs/SPEC.md](docs/SPEC.md) |
| 2 | Per-bug builds (Dockerfile + binaries + harness + grader) | done — **68 bugs, all grade-PASS** |
| 3 | MCP server (Go, 6 tools) | done — [tools/mcp-server/](tools/mcp-server/) |
| 3 | Python runner | done — [runner/](runner/) |
| 4 | Site integration | done — [docs/benchmark.html](docs/benchmark.html) |

## Corpus

68 git-tracked bugs, each with a full bundle (bench.yaml, description.txt,
grader/expected.yaml, harness/build.sh, Dockerfile, prebuilt binaries,
poc/poc.bin). Every bug grades PASS under 3-round unanimity with each K_b flag
firing. Run `./fb-bench list` for the full set and `./fb-bench grade-all` to
verify. The corpus spans multiple sanitizer classes (null-deref, heap-overflow,
OOB read, UAF, leak, stack-underflow, OOM, assert/abort, timeout, UBSan), build
systems (autoconf, amalgam, cmake, meson, chromium-gn), and languages
(C, C++, JS-via-C-amalgam). Prebuilt harness binaries live in git-lfs;
`fb-bench` auto-pulls them on first `grade`/`run`.

## What's verified

- MCP server speaks JSON-RPC 2.0 over stdio; all 6 tools work.
- `read_file` denies `grader/expected.yaml` and `grader/buggy_region.json`.
- `write_file` rejects writes outside `BENCH_WORKSPACE`.
- `grade()` drives all 4 oracles (reach / crash / class / site) with
  three-round unanimity across every bug.
- Runner CLI parses and imports cleanly.

## Next

- Wire up live (model, bug, seed) runs and publish a leaderboard.
