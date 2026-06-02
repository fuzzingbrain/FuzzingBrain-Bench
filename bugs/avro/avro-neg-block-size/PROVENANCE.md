# Provenance

**Bug**: Negative block size causes allocation-size-too-big in the Avro C datafile reader
**Upstream**: https://github.com/apache/avro/pull/3623
**Vuln commit**: 3af7a4654d574be7c78125e610a7d4ca23542eab

## Harness

`harness/datafile_fuzzer.c` writes the fuzz input to a tempfile, then
drives `avro_file_reader_fp()` → `avro_file_reader_get_writer_schema()`
→ `avro_generic_class_from_schema()` → loop of
`avro_file_reader_read_value()`.

## Triggering input

`poc/poc.bin` is the original 83-byte crash file
(`crash-3577d0faeb78d458118161991b604f04bbbd7745`): a valid Avro OCF
header (magic `Obj\x01`, schema `{"type":"null"}`, codec `null`, 16-byte
sync marker) followed by a block-count varint of 0 and a block-size
varint byte `0x01`, which zigzag-decodes to `-1`.

`file_read_block_count()` reads the block size as an `int64_t` and passes
it to the allocator without checking for a negative value. The `-1`
becomes `0xFFFFFFFFFFFFFFFF` when used as the allocation size, and
AddressSanitizer aborts with `allocation-size-too-big`.

## Observed crash (release-asan binary)

    ==PID==ERROR: AddressSanitizer: requested allocation size 0xffffffffffffffff ...
        #1 avro_default_allocator   lang/c/src/allocation.c:36
        #2 avro_file_reader_fp       lang/c/src/datafile.c:529
    SUMMARY: AddressSanitizer: allocation-size-too-big ... in realloc

At `-O2` (release-asan) `file_read_block_count()` is inlined into
`avro_file_reader_fp()`, so the top in-tree frame is datafile.c:529 (the
`file_read_block_count(r)` call site); the buggy allocation itself is at
datafile.c:459 inside `file_read_block_count()`.

## Build

Libraries and harness are built with `-fsanitize=address` only (plus the
libFuzzer driver for linking), matching the original report's
AddressSanitizer build. No UndefinedBehaviorSanitizer is used.
