# upx-pe-loadconf-overflow harness provenance

- **Source**: Issue body of https://github.com/upx/upx/issues/950 — section "Step 1: Create the PE Pack Fuzzer" provides `pack_pe_fuzzer.cpp`.
- **URL fragment**: https://github.com/upx/upx/issues/950#issue
- **Found in**: issue_body
- **Notes**: libFuzzer harness `pack_pe_fuzzer.cpp` targets the pack code path for PE32 binaries (writes input as `.exe`, runs `upx -1 -f -q -o <out> <in>`).
