# Sealed challenges — public challenge images + remote grading

Run FB-Bench publicly without ever shipping the answer key. Each bug splits into a
**public, answer-free challenge image** and a **private remote grading oracle**.
Users get only verdicts — never the PoC, the expected class/site, the fix, or the
ground-truth binaries.

## Architecture

```
  ┌─ challenge image (public, ghcr) ──────────┐        ┌─ grade server (private) ─┐
  │  src@vuln_commit + harness + bench.yaml*   │        │  binaries + expected.yaml │
  │  + mcp-server client                       │        │  + poc  (the answer key)  │
  │  agent reads source, crafts an input,      │        │                           │
  │  calls grade() ───────────────────────────┼─ POST ─┤  runs the harness oracle, │
  │                          ◄─── verdict ─────┼────────┤  returns ONLY the verdict │
  └────────────────────────────────────────────┘        └───────────────────────────┘
        * bench.yaml is scrubbed: no fix_commit / fix_patch
```

The agent never runs a binary and never sees an answer file. The only thing that
crosses the wire is the candidate input (out) and the capability verdict (back).

## Build (operator)

```bash
# one bug
python tools/sealed/build_challenge.py <bug_id> --grade-url https://grade.example/ 
# whole corpus + assemble the private oracle bundles
python tools/sealed/build_all.py --grade-url https://grade.example/
```
`build_challenge.py` runs a **leak audit** before every build and refuses to build
if any `poc/ grader/ binaries/ expected.yaml` or `fix_commit`/`fix_patch` would land
in the image (upstream `src/` is exempt — public OSS may carry `*.bin` fixtures).

## Run the grading oracle (private infra)

```bash
# oracle-root/<bug>/ holds each bug's answer bundle (binaries + expected.yaml + poc)
mcp-server -grade-server :8077 -oracle-root tools/sealed/oracle-root
# POST /grade?bug=<id> with the candidate bytes -> JSON capability verdict
```
The oracle root and its bundles are **gitignored** — they never enter the public repo.

## Use a challenge (end user)

```bash
docker run -it ghcr.io/<owner>/fbbench-challenge-<bug>:latest   # answer-free
# inside: your agent drives mcp-server over stdio (setup/read/list/write/exec/grade).
# grade() POSTs to BENCH_GRADE_URL and returns the verdict — no answers on this host.
```

## Verify

```bash
python tools/sealed/verify_sealed.py --grade-url http://localhost:8077
#  wire   : the bug's real PoC, POSTed to the oracle, fires its full K_b
#  leak   : `docker run` the image and assert no answer file is present
```

## Publish images

```bash
python tools/sealed/push_all.py --registry ghcr.io --owner <owner>
```

## Scope note — the git repo itself

These images make the *distribution* answer-free. The `bugs/` tree in this repo
still contains the answers (poc/grader/binaries/fix_commit) and so does git history.
Making the *public repository* answer-free (private answer repo + public challenge-
only repo, or history rewrite) is a separate, deliberate step — see PLAN.md.
