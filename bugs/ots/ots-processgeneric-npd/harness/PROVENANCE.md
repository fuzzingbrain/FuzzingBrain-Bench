# ots-processgeneric-npd harness provenance

- **Source**: Issue body of https://github.com/khaledhosny/ots/issues/308 — section "Reproduction Steps" provides the harness `fuzz_ots_passthru.cc`.
- **URL fragment**: https://github.com/khaledhosny/ots/issues/308#issue
- **Found in**: issue_body
- **Notes**: libFuzzer harness `fuzz_ots_passthru.cc` exercises `OTSContext::Process()` after setting every possible 4-char tag and tag 0 to `TABLE_ACTION_PASSTHRU` (which hits the never-tested passthrough code path). bench-corpus.json had labelled the harness `ots-fuzzer.cc` (default-mode OSS-Fuzz harness); the reporter explicitly notes "The existing `ots-fuzzer` (which uses the default mode) never found this bug because it doesn't exercise the passthrough code path."
