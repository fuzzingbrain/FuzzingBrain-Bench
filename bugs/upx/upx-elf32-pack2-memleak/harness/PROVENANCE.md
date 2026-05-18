# upx-elf32-pack2-memleak harness provenance

- **Source**: The harness `pack_file_fuzzer` is referenced by name in issue body of https://github.com/upx/upx/issues/945 (reproduction step `./pack_file_fuzzer crash_input_memleak.elf`). The source code itself is not pasted in #945 but is included verbatim in the sibling FuzzingBrain upx issue #947 (an ELF64 bug filed alongside this one).
- **URL fragment**: https://github.com/upx/upx/issues/945#issue (named) + https://github.com/upx/upx/issues/947#issue (source)
- **Found in**: issue_body (referenced) + sibling issue (source)
- **Notes**: Same pack-file fuzzer is used for all four upx FuzzingBrain bugs (945, 946, 947, 950). Replicated from #947.
