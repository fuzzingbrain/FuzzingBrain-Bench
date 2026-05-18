# jsonjava-jsonml-classcast harness provenance

- **Source**: Issue body of https://github.com/stleary/JSON-java/issues/1034 — section "Trigger Method 2: Fuzzer (Jazzer)".
- **URL fragment**: https://github.com/stleary/JSON-java/issues/1034#issue
- **Found in**: issue_body
- **Notes**: Jazzer harness `JsonMLFuzzer.java` calls `JSONML.toJSONArray(input)` and only catches `JSONException` so `ClassCastException` propagates. Note: bench-corpus.json lists OSS-Fuzz's `JsonJavaFuzzer.java` as covering this code path; the reporter's harness here is a smaller per-bug harness from the issue body.
