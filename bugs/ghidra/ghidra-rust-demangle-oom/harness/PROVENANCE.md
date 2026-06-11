# ghidra-rust-demangle-oom harness provenance

- **Source**: Advisory body of https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442 — section "Trigger Method 2: Fuzzer (libFuzzer + AddressSanitizer)".
- **URL fragment**: GHSA-m94m-fqr3-x442 (advisory body)
- **Found in**: advisory_body
- **Notes**: libFuzzer harness `fuzz_rust_demangle.c` calls `rust_demangle()` on inputs with `DMGL_VERBOSE`. Both ghidra-rust-demangle-oom and binutils-rust-demangle-oom share this same advisory and same harness.
