# upx-pe-resource-memleak harness provenance

- **Source**: Issue body of https://github.com/upx/upx/issues/946 references `test_packed_file_fuzzer` (upstream OSS-Fuzz harness) for reproduction. Note: this is **NOT** the FuzzingBrain pack-file fuzzer — the maintainer's upstream OSS-Fuzz `test_packed_file_fuzzer.cpp` covers the unpack/test path which reaches the resource conversion code. The FuzzingBrain pack-file fuzzer is also applicable; replicated here for consistency with other upx entries.
- **URL fragment**: https://github.com/upx/upx/issues/946#issue
- **Found in**: issue_body (only `test_packed_file_fuzzer` named, no source) — pack_file_fuzzer.cpp source replicated from sibling issue #947
- **Notes**: bench-corpus.json review notes flag this as "Maintainer closed issue with 'Done' but no commit referenced; status uncertain." Reporter does not paste the OSS-Fuzz `test_packed_file_fuzzer.cpp` source.
