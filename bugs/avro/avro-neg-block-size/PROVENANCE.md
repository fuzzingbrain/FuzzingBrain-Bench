# Provenance

**Bug**: Null pointer member access during avro_file_reader_fp() setup
**Upstream**: https://github.com/apache/avro/pull/3623
**Vuln commit**: 3af7a4654d574be7c78125e610a7d4ca23542eab

## Harness

`harness/datafile_fuzzer.c` writes the fuzz input to a tempfile, then
drives `avro_file_reader_fp()` → `avro_file_reader_get_writer_schema()`
→ `avro_generic_class_from_schema()` → loop of
`avro_file_reader_read_value()`.

## Triggering input

`poc/poc.bin` is 4 bytes: `0a 08 08 0a`. Discovered by libFuzzer in ~2s
from an empty corpus. Avro container files start with the magic
`Obj\x01`; our payload bypasses that and instead exercises a path in
`file_read_header()` where `avro_read()` ends up dereferencing a NULL
`_avro_reader_file_t*` at io.c:270.

## Notes

The PR title mentions "negative block size" as the headline issue.
What the harness actually catches first is an earlier null-deref in
the header-reading path during `avro_file_reader_fp()` setup. Both
are real bugs in the same code (datafile reader on malformed input);
the sanitizer fires at the io.c symptom site rather than the
datafile.c root cause. expected.yaml is set against the observed
site/class so the oracle is deterministic.
