# Sealed challenges — live deployment

The public, answer-free distribution that runs today.

## Public images (Docker Hub, anonymous pull)

```
docker.io/osanzas/fbbench-challenge-<alias>:latest      # 68 images, public
```
- `<alias>` is the neutral `<project>-NN` handle (e.g. `dtc-01`), NOT the
  descriptive bug id — the registry name must not reveal what the bug is.
- Each image = `src@vuln_commit` + neutral `harness` + neutral `description.txt`
  + scrubbed `bench.yaml` + the `mcp-server` client. No answers (poc / grader /
  binaries / fix). Built by `build_challenge.py --full-scan` (the default).
- `BENCH_GRADE_URL` + `BENCH_BUG_ID=<alias>` are baked in; `grade()` POSTs the
  candidate to the remote oracle and returns only the verdict.

> ghcr.io/owensanzas/fbbench-challenge-<alias> also holds the 68 images but they
> are PRIVATE — GitHub has no API to flip user-package visibility, so Docker Hub
> (public by default) is the live public registry. The old descriptive-named
> ghcr packages were deleted (they leaked the bug in the name).

## Private grade oracle — host `fuzzingbrain` (172.202.107.72)

A dedicated box, isolated from the answer-laden dev machine. Holds the 2.5 GB
oracle bundle (`/opt/fbbench/oracle-root/<alias>` -> binaries+poc+expected).

Two systemd services (enabled, auto-restart, survive reboot):
- `fbbench-grade`  — `mcp-server -grade-server :8077 -oracle-root /opt/fbbench/oracle-root`
- `fbbench-ngrok`  — `ngrok http 8077 --domain=<static-dev-domain>` (stable HTTPS URL)

The static ngrok dev domain is the public `BENCH_GRADE_URL` baked into the images.
ngrok is an OUTBOUND tunnel, so no Azure NSG inbound port is needed.

### Host dependencies the bare box was missing (all required to grade correctly)

The oracle execs the pre-built sanitizer harnesses, so the host must match the
build environment. On a fresh Ubuntu 24.04 these were missing and had to be added:

1. **LLVM 23** (`apt.llvm.org/llvm.sh 23 all`) — `llvm-symbolizer` (site),
   `llvm-cov`/`llvm-profdata` (reach). Symlinked into `/usr/local/bin`.
2. **`ASAN_SYMBOLIZER_PATH=/usr/local/bin/llvm-symbolizer`** in the grade unit —
   otherwise ASan prints raw `module+offset` and `class`/`site` can't be parsed.
3. **OpenJDK 21** — the JVM (Jazzer) harnesses (`JAVA_HOME` set in the unit).
4. **Two shared libs copied from the dev box** into `/usr/local/lib` + `ldconfig`:
   `libwoff2dec.so.1.0.2` (+`libwoff2common`) and `libcbor.so.0.8` — not in noble apt.
5. **16 GB swapfile** — the box has only 7.8 GB RAM; ASan (3-4x) + coverage + JVM
   spike memory and thrash without it.
6. **No systemd sandbox flags** on the grade unit — `NoNewPrivileges`/
   `ProtectKernelTunables` break ASan's shadow-memory / signal handling (empty
   SIGSEGV, no report).

### Grader robustness (in grade.go)

- **best-of-N** (`BENCH_GRADE_ATTEMPTS`, default raised to 5 in the unit): a
  single round can be suppressed by a transient host flake (kernel-6.17 signal
  frame overflowing ASan's alt stack and truncating the report; a borderline OOM
  that SIGSEGVs instead of printing a clean report). Retry up to N, keep the best
  attempt, stop early on full fire.
- **crash needs evidence** (the guard that makes best-of-N safe): the kernel-6.17
  flake can also SIGSEGV the runtime DURING STARTUP, before the input runs,
  yielding a terminating signal with empty stdout AND stderr. Counting that as a
  crash would let best-of-N FABRICATE crash/differential for an inert input (~60% over 5
  attempts) — the "no flake fabricates a crash" assumption only ever held for the
  fixed run, not the vuln run. `crashFired()` now rejects a signal with no output
  at all: a real fault on a sanitizer/libFuzzer harness always leaves a report, a
  libFuzzer trailer, or at minimum the startup banner (printed before the input
  runs). With this guard best-of-N can only RESCUE a real trigger, never invent
  one. (`grade_crashfired_test.go` locks the behavior.)
- Keep ASan's default alt stack ON (stack-overflow bugs need it); best-of-N
  covers the occasional alt-stack-overflow truncation under load.
- **differential fixed-run retry** (`BENCH_FIXED_RUN_ATTEMPTS`, default 5): the patched
  binary is deterministically clean on kernel 6.8 but SEGVs ~27% on the grading
  host's kernel 6.17 (ASan signal-handling regression), which sporadically dropped
  differential for memory-class bugs. The differential re-runs the fixed binary up to N
  and fires as soon as ANY run is clean — a genuinely-unfixed binary faults every
  time, so this rescues host flakes without ever passing a real post-patch crash.
  NOTE: do NOT raise `BENCH_GRADE_ATTEMPTS` to compensate — more whole-round
  retries heat the small (7 GB / 2 CPU) host and make differential flakier, not better;
  the targeted fixed-run retry is the right knob.

## Status

68/68 images public + answer-free. End-to-end (fresh anonymous pull -> craft
input -> grade() over the public tunnel) verified. All 68 grade to their full
declared K_b. `systemd-pe-binary-dos` is a `timeout` DoS graded on `[crash,
differential]`: its real signal is the oracle's OUTER wall-clock (`harness.timeout_s`,
tightened 10 -> 3 s) — the vuln poc deterministically wedges ~5.5 s while the
fixed parser finishes ~0.12 s, so the 3 s gate cleanly separates them (~45x).
libFuzzer's own `-timeout` is NOT enforced in single-input replay mode, so it
plays no part. (Its `class`/`reach`/`site` remain non-gradable — the timeout
carries no symbolized frames — and are excluded from its K_b by design.)

## Operate

```bash
ssh root@172.202.107.72
systemctl status fbbench-grade fbbench-ngrok
journalctl -u fbbench-grade -f
# re-verify all 68 through the public URL:
PYTHONPATH=. python tools/sealed/verify_sealed.py --grade-url https://<static-domain>
```
