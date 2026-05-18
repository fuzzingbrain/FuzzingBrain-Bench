# mongoose-mg-match-overflow harness provenance

- **Source**: Issue body of https://github.com/cesanta/mongoose/issues/3393 — only references the harness binary by name. ASan stack trace names the source files:
  - `fuzz_path_sanitization` is at `/src/mongoose/fuzz_security.c:196`
  - `LLVMFuzzerTestOneInput` is at `/src/mongoose/fuzz_security.c:331`
- **URL fragment**: https://github.com/cesanta/mongoose/issues/3393#issue
- **Found in**: not_found (only filename `fuzz_security.c` is named in the stack trace; the harness source is not pasted in the report)
- **Notes**: Harness filename `fuzz_security.c` is FuzzingBrain-authored per bench-corpus.json review notes (not one of upstream OSS-Fuzz's two harnesses `fuzz` from `test/fuzz.c` or `fuzz_netdriver_http`). No source code is attached to the issue.
