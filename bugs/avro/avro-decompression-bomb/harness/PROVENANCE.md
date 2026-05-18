# avro-decompression-bomb harness provenance

- **Source**: PR body of https://github.com/apache/avro/pull/3625 (issue body / PR description)
- **URL fragment**: https://github.com/apache/avro/pull/3625#issue (in section "Trigger Method 2: Fuzzer (oss-fuzz / Jazzer)")
- **Found in**: issue_body
- **Notes**: Jazzer harness `DecompressionBombFuzzer` exercises `DataFileReader` via `SeekableByteArrayInput`. Provided as code block under heading "Trigger Method 2".
