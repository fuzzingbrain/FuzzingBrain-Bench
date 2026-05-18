# jq-dump-op-npd harness provenance

- **Source**: Issue body of https://github.com/jqlang/jq/issues/3458 — only states "Fuzzer: OSS-Fuzz jq fuzzer" and shows a Python generator for the trigger input. The actual `--debug-dump-disasm` is what triggers via the jq CLI; the OSS-Fuzz harness source code is not pasted in the report.
- **URL fragment**: https://github.com/jqlang/jq/issues/3458#issue
- **Found in**: not_found
- **Notes**: Only the jq CLI reproducer (`jq --debug-dump-disasm -n -f poc.jq`) and a Python PoC-generator are provided. No fuzzer C source. The bench-corpus.json best-guess for the OSS-Fuzz harness is `jq_fuzz_compile.c` (lives at https://github.com/jqlang/jq/blob/master/src/jq_fuzz_compile.c), but that source is upstream-jq, not pasted into the report.
