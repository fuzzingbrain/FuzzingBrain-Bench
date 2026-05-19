# Provenance

**Bug**: Unbounded recursion / OOM in demangle_binder via deeply-nested v0 mangling
**Upstream**: https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442
**Vuln commit**: caeeac88ddb5b004736de440db86380ff6e61229

## Build

Identical to ghidra-rust-demangle-oom: curl-fetches the 5 needed
libiberty source files from Ghidra's vendored copy. Same 4 binaries.

## Triggering input

`poc/poc.bin` is 36 bytes — `_RYTRjYFFGFFYTTE_ZTVeee\0beeeYTEEYtUY`.
The leading `_R` enters the v0 path; nested type/path tokens drive the
demangler into mutually-recursive `demangle_path` ↔ `demangle_type` ↔
`demangle_binder`. libFuzzer's per-input wall-clock fires before
completion and stderr ends with `SUMMARY: libFuzzer: timeout`.

## Invocation gotcha

bench.yaml's `invocation` is `["-timeout=10", "@@"]` so libFuzzer
enforces its own per-input timeout *inside* the grader's 30s wrapper.
Without the explicit `-timeout`, libFuzzer's default 1200s would
exceed the wrapper and the harness would be SIGKILL'd before printing
its timeout summary, leaving the oracle blind. Pattern is reusable
for other unbounded-loop bugs.

## Notes

Sibling of ghidra-rust-demangle-oom. Same advisory, same harness,
same source tree, different input shape and different bug class:
rust-demangle-oom fires a null-deref UBSan at str_buf_append:1576
on short v0 inputs; cplus-demangle-oom fires an OOM-class libFuzzer
timeout in demangle_binder:664 on deeply-nested v0 inputs.
