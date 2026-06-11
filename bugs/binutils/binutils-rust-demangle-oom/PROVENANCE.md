# Provenance

**Bug**: OOM in rust_demangle via unbounded lifetime count in demangle_binder (CWE-400)
**Upstream**: https://sourceware.org/bugzilla/show_bug.cgi?id=33878
**Vuln commit**: 96c87c6dd55c38519ad168230d0893797b62fd52
**Upstream fix**: binutils-gdb 74b48014179ed612ed0ea6ee4abf3b2102ef764d

## Harness

`harness/fuzz_rust_demangle.c` is the libFuzzer harness from the cross-
linked Ghidra advisory GHSA-m94m-fqr3-x442 (Bugzilla 33878 itself is
gated). Calls `rust_demangle(input, DMGL_VERBOSE)` on a NUL-terminated
copy of the fuzz input.

## Build

`libiberty/rust-demangle.c` is fully self-contained — it only pulls in
`safe-ctype.h/c` and the public `demangle.h`. The build compiles those
three TUs directly into the harness; no autotools or libbfd needed.
Sourceware's CDN 502s on partial-clone (`--filter=tree:0`), so the
Dockerfile does a plain `git clone` and checks out the vuln SHA.

The original upstream fault is a libFuzzer **out-of-memory**, NOT an
ASan/UBSan error. The harness is therefore built with the fuzzer driver
only (`-fsanitize=fuzzer`, no address/undefined). libFuzzer's default
`rss_limit_mb` (2048) detects the OOM and aborts.

## Triggering input

`poc/poc.bin` is the original 61-byte OOM PoC from the upstream record
(`_RINvC4te_C4tokpppppppppppFFFFFFGFpppppppppKj2_FFFFFFFFFFFFFE`).
Six nested `F` function types reach `demangle_binder()`, which then
decodes a 13-digit base-62 integer after the `G` tag as the bound
lifetime count. The loop appends lifetime text into an output buffer
that `str_buf_reserve()` doubles without limit, driving ~35,000,000x
amplification (61 bytes -> >2 GB) until the rss limit is exhausted.

## Crash signature

```
==PID== ERROR: libFuzzer: out-of-memory (used: ~2074Mb; limit: 2048Mb)
SUMMARY: libFuzzer: out-of-memory
```

Root cause: `demangle_binder()` (rust-demangle.c:646-665, unbounded
input-controlled loop count) -> `print_lifetime_from_index` ->
`str_buf_append` -> `str_buf_reserve` realloc (rust-demangle.c:1553).

## Notes

The rss-based OOM banner carries no symbolized stack frames, and the
coverage profile cannot flush before the OOM kill, so only the
`crash` + `class` capabilities are machine-gradable (same as the sibling
`ghidra-rust-demangle-oom`). expected.yaml grades `class: oom`.

A previous version of this bug was over-built with
`-fsanitize=fuzzer,address,undefined` and graded a neighboring UBSan
"applying zero offset to null pointer" in `str_buf_append` against a
17-byte PoC. That was unfaithful to the OOM record
(OOM-rust-demangle-20260127) and has been corrected here.
