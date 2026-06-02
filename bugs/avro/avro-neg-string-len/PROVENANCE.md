# Provenance

**Bug**: Negative string length -> allocation-size-too-big in the Avro C binary value reader
**Upstream**: https://github.com/apache/avro/pull/3622
**Vuln commit**: f7dfbc0d37608a896ffcc8734a8d64376c463039
**Original sanitizer**: AddressSanitizer (asan-only)

## Harness

`harness/value_reader_fuzzer.c` keeps 20 hardcoded Avro schemas and
selects one with `data[0] % NUM_SCHEMAS`, then feeds the remaining
bytes to `avro_value_read()`.

## Triggering input

`poc/poc.bin` is the original upstream crash input, 4 bytes: `34 01 00 2f`
(crash-93f03eb99c1ed19212410db31a6888adb995a272 from the upstream report).

- `0x34`: schema selector, `52 % 20 = 12` = `{"type":"map","values":"string"}`
- `0x01`: map block count varint -> zigzag -1 -> negated, one entry
- `0x00`: map block size varint -> 0
- `0x2f`: string-length varint -> zigzag decodes to -24

`read_string()` does `*len = str_len + 1` (= -23) and calls
`avro_malloc(*len)`; the negative value cast to `size_t` becomes
`0xFFFFFFFFFFFFFFE9`, and the underlying `realloc` trips
AddressSanitizer's allocation-size-too-big check.

## Crash (release-asan, -fsanitize=address only)

```
==PID==ERROR: AddressSanitizer: requested allocation size 0xffffffffffffffe9
    ... exceeds maximum supported size ...
    #1 avro_default_allocator   lang/c/src/allocation.c:36
    #2 read_map_value           lang/c/src/value-read.c:103   <- read_string() call site (inlined)
    #3 read_value               lang/c/src/value-read.c:368
    #4 avro_value_read          lang/c/src/value-read.c:391
SUMMARY: AddressSanitizer: allocation-size-too-big in realloc
```

`read_string()` (encoding_binary.c:172-186, the documented root-cause
function) is inlined at -O1 into `read_map_value`, so the closest
library frame the sanitizer reports is its call site at value-read.c:103.

## Notes

This is the original PR #3622 bug. The build is AddressSanitizer-only
(no UBSan) to match the upstream discovery sanitizer, and the grader
checks reach + crash + site (class is omitted because ASan reports the
allocation-size-too-big banner as the bare token "requested", which is
outside the oracle's class vocabulary — same convention as
imagemagick-kernelinfo-alloc).
