# Provenance

**Bug**: Null pointer arithmetic in str_buf_append()
**Upstream**: https://sourceware.org/bugzilla/show_bug.cgi?id=33878
**Vuln commit**: 96c87c6dd55c38519ad168230d0893797b62fd52

## Harness

`harness/fuzz_rust_demangle.c` is the libFuzzer harness from the cross-
linked Ghidra advisory GHSA-m94m-fqr3-x442 (Bugzilla 33878 itself is
gated). Calls `rust_demangle(input, DMGL_VERBOSE)` on a NUL-terminated
copy of the fuzz input.

## Build trick

`libiberty/rust-demangle.c` is fully self-contained — it only pulls in
`safe-ctype.h/c` and the public `demangle.h`. The build compiles those
three TUs directly into the harness; no autotools or libbfd needed.
Sourceware's CDN 502s on partial-clone (`--filter=tree:0`), so the
Dockerfile does a plain `git clone` and checks out the vuln SHA.

## Triggering input

`poc/poc.bin` is 17 bytes (`_RC0RCzBB5\0004\000\`Z0N`). Discovered by
libFuzzer in ~25s from an empty corpus. The v0 Rust prefix `_R` is
enough to take the demangler into the path that hits the
zero-capacity `str_buf_t` arithmetic UB.

## Notes

PR title in upstream bench-corpus references an OOM via unbounded
lifetime count. What this harness actually surfaces first is a UBSan
"applying zero offset to null pointer" in `str_buf_append` — a
neighboring bug in the same demangler. expected.yaml is set against
the observed site/class so the oracle is deterministic.
