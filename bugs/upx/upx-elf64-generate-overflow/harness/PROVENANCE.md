# upx-elf64-generate-overflow harness provenance

- **Source**: Issue body of https://github.com/upx/upx/issues/947 — section "Alternative: Using libFuzzer harness" provides `pack_file_fuzzer.cpp`.
- **URL fragment**: https://github.com/upx/upx/issues/947#issue
- **Found in**: issue_body
- **Notes**: libFuzzer harness `pack_file_fuzzer.cpp` writes the fuzz input to a temp file then invokes `upx_main` with `-1 -f -q` to drive the pack code path (which is not covered by upstream OSS-Fuzz's existing decompress-only fuzzers).
