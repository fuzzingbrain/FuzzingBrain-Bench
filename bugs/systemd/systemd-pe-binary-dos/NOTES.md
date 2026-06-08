# systemd-pe-binary-dos — build-feasibility notes

## Build feasibility risk (FLAG)

systemd is a **large** project. Even a minimal libFuzzer build pulls in
`libsystemd-shared`, so `build-libs` compiles a large fraction of the
tree (hundreds of objects, several minutes on a multi-core host). This is
heavier than the other bench entries and is the main feasibility risk.

There is **no faithful lighter path**: the harness (`fuzz-pe-binary.c`)
`#include`s systemd-internal headers (`pe-binary.h`, `uki.h`,
`alloc-util.h`, `crypto-util.h`, `fd-util.h`, `fuzz.h`, `memfd-util.h`,
`tests.h`) and calls `pe_load_headers` / `pe_load_sections` /
`pe_read_section_data_by_name` / `uki_hash`, which live in
`src/shared/pe-binary.c` and depend on generated config + the
`basic`/`shared` static libs. Building through Meson via the upstream
`simple_fuzzers` machinery is the only faithful option.

## OpenSSL is required

The expensive loop lives in `uki_hash()`, which is gated on
`HAVE_OPENSSL`. `libssl-dev` MUST be installed (it is, in the Dockerfile)
or the hot path is `#if`'d out and the slow-unit will not reproduce.

## How the harness is wired

`fuzz-pe-binary.c` is the exact libFuzzer target upstream added in PR
#42348 at `src/fuzz/fuzz-pe-binary.c`. At the **vuln_commit**
(`97a0ec135b1a3330abe8c34794c6e31b266452fc`, parent of the fix) that file
does **not** exist yet — only the buggy `src/shared/pe-binary.c` does.
`build.sh` creates the harness at the canonical path and appends it to
the `simple_fuzzers += files(...)` block in `src/fuzz/meson.build`, then
builds with `-Dllvm-fuzz=true`. The resulting binary is `fuzz-pe-binary`.

## Slow-unit / timeout oracle

This is an algorithmic-complexity DoS, not a memory-safety fault. The
unit does **not** return on its own, so the harness must be run under
libFuzzer's wall-clock alarm — `bench.yaml` sets
`invocation: ["-timeout=10", ...]`. The observable signature is a
`libFuzzer: timeout` banner (no symbolized frames), which is why the
capability set is the minimal `[crash, class]` with `class: timeout`,
`sanitizer: libfuzzer`. The true hot loop (`while (remaining > 0)` in
`uki_hash`, ~4.17M 1024-byte SHA-256 updates) is recorded in
`grader/expected.yaml` for documentation only.

## Reproduction expectation

The shipped `poc/poc.bin` is the canonical 382-byte PE32+ reproducer
(sha256 c1388d74723d7d6c687a677fce599664697003ab61b808fd4c7b14c918415a1a,
the same `crash_input.bin` from the record). Pre-fix it wedges
`uki_hash` for >10 s; post-fix (#42348) the input is rejected in
milliseconds.

## NOT done here (per task scope)

No docker build, no compile, no commit. All seven files authored
faithfully; the build path is documented but unverified.
