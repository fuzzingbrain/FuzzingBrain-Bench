# Notes / gaps — flatbuffers-parser-deserialize-uaf

- **vuln_commit**: No exact commit was recorded in the source record
  (`projects/chromium/flatbuffers-double-free-parser-deserialize/vuln.yaml`
  has only dates and the GitHub issue link #9009). The flatbuffers chrome
  fuzzing campaign pinned its source tree at
  `bab10754d93d74d1ff44d46de63558bc4127f7d8` (from the repro-bundle
  `method.yaml` files). `bench.yaml` leaves `vuln_commit: ""`; the
  Dockerfile uses the campaign-pinned commit as a best-effort default.
- **poc.bin**: copied verbatim from the record's
  `crash-bfd486276e2e0976e0d141e7c31b9221bf2f84c8` (284 bytes), which is
  the libFuzzer-format input (2-byte flags/json-ratio header + .bfbs).
  `poc/poc_pure_schema.bfbs` is the record's pure 176-byte schema
  (`crash_double_free.bfbs`) used for the standalone production reproducer;
  the harness in this benchmark consumes the header-prefixed form.
- The record's `crash-NOTE.txt` states the original fuzzer artifact was not
  persisted outside the container; re-fuzzing confirmed the same code path
  (Binary Reproduction = PARTIAL in the report).
- ASan classifies this as "attempting double-free" in the fuzzer build and
  as "heap-use-after-free" in the production build (same ownership bug).
  Grader keyed to `use-after-free`.
