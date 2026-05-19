# Provenance

**Bug**: NULL pointer member access in avro_schema_union_append()
**Upstream**: https://github.com/apache/avro/pull/3622
**Vuln commit**: f7dfbc0d37608a896ffcc8734a8d64376c463039

## Harness

`harness/value_reader_fuzzer.c` keeps ~20 hardcoded Avro schemas and
selects one with `data[0] % NUM_SCHEMAS`, then feeds the remaining
bytes to `avro_value_read()`. When the selected schema is a union
(e.g. `["null","string"]`), the schema parser itself UBSan-fails
inside `avro_schema_union_append()` before any value-read work happens.

## Triggering input

`poc/poc.bin` is 2 bytes: `0x3a 0x0a`. Discovered by libFuzzer in ~2s.
The first byte (58) mod 21 = 16, which selects union schema #16.

## Notes

PR #3622's headline is "negative string length OOB" in the value
reader. The harness as written catches an earlier UBSan finding in
the schema parser — same project, same C library, related code path,
but a different precise site than the PR title suggests. PROVENANCE
makes the divergence explicit so expected.yaml is consistent with
observed behavior.
