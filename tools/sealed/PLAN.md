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

## Status — COMPLETE (mechanism)
- [x] P0 split defined
- [x] P1 remote grade server (mcp-server -grade-server)
- [x] P2 grade() remote proxy (BENCH_GRADE_URL)
- [x] P3 challenge Docker image (answer-free, baked client + BENCH_GRADE_URL)
- [x] P4 proven end-to-end (dtc C / flatbuffers C++ / pdfbox JVM)
- [x] P5 **68/68 challenge images built, 0 leaks; 68/68 wire OK** (real PoC -> remote
      oracle fires full K_b); pushing to ghcr.io/owensanzas/fbbench-challenge-<bug>.

Scaling bug found+fixed in batch: copytree(symlinks=False) dereferenced upstream dir
symlinks (graal-nodejs etc.) -> a single bundle ballooned to 16 GB; symlinks=True ->
33 MB. (Exactly why prototype-then-batch: 3 prototype bugs didn't surface it.)

## REMAINING — repo itself (NOT done autonomously; irreversible, needs a decision)
These images make the *distribution* answer-free, but `bugs/` + git HISTORY still carry
the answers. Making the public *repo* answer-free needs either a history rewrite
(destructive, irreversible on a public repo) or a public(challenge-only)/private(answer)
repo split. Flagged for an explicit call — not bulldozed under "全部搞定".

## Leak-audit rule (for batch)
Flag ONLY a bug's OWN answer artifacts: `poc/`, `grader/`, `binaries/`, and `fix_commit`/`fix_patch`
in bench.yaml. Do NOT flag files under `src/` (upstream source can contain *.bin test fixtures).
