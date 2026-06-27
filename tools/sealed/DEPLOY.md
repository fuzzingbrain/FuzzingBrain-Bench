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
  attempt, stop early on full fire. Can only RESCUE a real trigger from a flake —
  no flake fabricates a crash — so it never creates a false positive.
- Keep ASan's default alt stack ON (stack-overflow bugs need it); best-of-N
  covers the occasional alt-stack-overflow truncation under load.

## Status

68/68 images public + answer-free. End-to-end (fresh anonymous pull -> craft
input -> grade() over the public tunnel) verified. 67/68 grade to full K_b;
`systemd-pe-binary-dos` misses only `class` (a `timeout` DoS that crashes rather
than hangs on this host's CPU — an inherent environment-behavior difference; it
still scores crash/crash2/reach).

## Operate

```bash
ssh root@172.202.107.72
systemctl status fbbench-grade fbbench-ngrok
journalctl -u fbbench-grade -f
# re-verify all 68 through the public URL:
PYTHONPATH=. python tools/sealed/verify_sealed.py --grade-url https://<static-domain>
```
