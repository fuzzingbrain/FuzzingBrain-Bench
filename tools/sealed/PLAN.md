# Sealed challenges — public challenge images + remote grading

**Branch:** `feat/sealed-challenges` · **Started:** 2026-06-25 · ExploitBench-style.

## Goal
FB-Bench public, but answers NEVER leak (no pretraining contamination, no cheating).
User sees only scores. Decision (user): **public challenge image + REMOTE grading**;
**prototype 1-2 then batch all 68, NO STOP.**

## The split (proven on dtc)
- **CHALLENGE (public, per-bug image):** `src/` (library source @ vuln_commit — public OSS),
  `harness/` (our driver), `description.txt`, scrubbed `bench.yaml` (no fix_commit/fix_patch).
  This is exactly what `stage_bug_view()` already produces — answer-free by construction.
- **ORACLE (private, remote service):** `binaries/{release-asan,fixed-asan,coverage}/harness`,
  `grader/expected.yaml`, `poc/`. Held behind the grade server. The answer key never ships.
- The agent never runs a binary; it reads source and submits candidate inputs to `grade()`,
  which on the sealed path is a network call to the oracle.

## Wire (built + proven)
`tools/mcp-server` gained:
- **client:** `grade()` → if `BENCH_GRADE_URL` set, POST candidate bytes to the oracle, return its
  verdict (gradeRemote in gradeserver.go). No local oracle touched. `BENCH_BUG_ID` selects the bug.
- **oracle server:** `mcp-server -grade-server :PORT -oracle-root DIR` serves
  `POST /grade?bug=<id>` — writes the posted bytes to a temp workspace, points oracleDir at
  `DIR/<id>`, runs the SAME toolGrade locally, returns the verdict. 100% logic reuse.

Proven 2026-06-25: dtc real PoC → 5/5 fired; junk → 0; libpng real PoC → 5/5 — all via the remote
server with NO local answers on the client. Answer-free bundle confirmed (only false-positive was
dtc's own upstream test fixture src/tests/incbin.bin, not our PoC).

## Status
- [x] P0 split defined
- [x] P1 remote grade server (mcp-server -grade-server)
- [x] P2 grade() remote proxy (BENCH_GRADE_URL)
- [~] P3 challenge Docker image (answer-free, baked client + BENCH_GRADE_URL)
- [ ] P4 prove agent episode against the image
- [ ] P5 batch 68 + push challenge images to registry + load oracle bundles

## Leak-audit rule (for batch)
Flag ONLY a bug's OWN answer artifacts: `poc/`, `grader/`, `binaries/`, and `fix_commit`/`fix_patch`
in bench.yaml. Do NOT flag files under `src/` (upstream source can contain *.bin test fixtures).
