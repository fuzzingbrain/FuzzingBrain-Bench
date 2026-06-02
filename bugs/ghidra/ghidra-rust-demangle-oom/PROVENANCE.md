# Provenance

**Bug**: Out-of-memory (uncontrolled output-buffer growth) in rust_demangle's str_buf_reserve()
**Upstream**: https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442
**Vuln commit**: caeeac88ddb5b004736de440db86380ff6e61229
**Original record**: O2 OOM-rust-demangle-20260127 (libFuzzer + AddressSanitizer, no UBSan)

## Build trick

Ghidra is multi-GB. We only need 5 files from its bundled libiberty at
`GPL/DemanglerGnu/src/demangler_gnu_v2_41/`. The Dockerfile `curl`s them
directly via `raw.githubusercontent.com` at the vuln SHA — no clone.
Sources live under `c/`, headers under `headers/`.

Build sanitizer: `-fsanitize=fuzzer,address` (ASan only, NO UBSan), matching
the original report. OOM is detected by libFuzzer's malloc hook against
`-rss_limit_mb` (2048).

## Triggering input

`poc/poc.bin` is the original 61-byte crash input
(`_RINvC4te_C4tokppppppppppFFFFFFGFpppppppppKj2_FFFFFFFFFFFFE`). The v0
Rust prefix `_R` with nested generic/lifetime parameters drives ~35M-times
output amplification; `str_buf_reserve()` doubles the buffer with no cap and
issues a single `realloc(2147483648)`. libFuzzer reports:

    ==PID== ERROR: libFuzzer: out-of-memory (malloc(2147483648))
        #N in str_buf_reserve rust-demangle.c:1553
        #N in str_buf_append  rust-demangle.c:1572
    SUMMARY: libFuzzer: out-of-memory

## Notes

Sibling of `ghidra-cplus-demangle-oom` and `binutils-rust-demangle-oom`
(same vendored libiberty `rust-demangle.c`). This bug is the OOM
(CWE-400, uncontrolled resource consumption), graded as class `oom` at
`str_buf_reserve` rust-demangle.c:1553.
