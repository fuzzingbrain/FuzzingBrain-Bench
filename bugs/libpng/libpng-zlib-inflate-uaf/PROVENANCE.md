# Provenance — libpng-zlib-inflate-uaf

- **Upstream advisory:** https://github.com/pnggroup/libpng/security/advisories/GHSA-qvg3-h654-xq3j
- **CVE:** CVE-2026-46675 (High)
- **Fixed in:** libpng 1.6.59 / 1.8.0 (trunk). Vulnerable range: `>= 1.6.0, < 1.6.59`
  (confirmed via `gh api /repos/pnggroup/libpng/security-advisories/GHSA-qvg3-h654-xq3j`).
- **vuln_commit:** `614ab644f8092128719264775795c5243e06878e`
  ("Merge tag 'v1.6.58' into libpng18", 2026-04-15) — bug PRESENT (predates the 1.6.59 fix).
- **Discovery:** AGF (AI-Guided Fuzzing, Aisle Research). Reporter: Ze. Found 2026-04-14,
  submitted 2026-04-24, fixed upstream 2026-05-01.
- **Origin record:** `O2_Vulnerability_Management/agf-results/projects/oss-fuzz/libpng/use-after-free-png_zlib_inflate/`

## Root cause

libpng chunk handlers share one scratch buffer (`png_ptr->read_buffer`). A `zTXt`
chunk allocates it and the inflate state stores its address in `zstream.next_in`;
a following `pCAL` chunk calls `png_read_buffer` again, freeing that buffer without
clearing `zstream.next_in`. Later IDAT processing (`png_read_end` →
`png_read_finish_IDAT` → `png_read_IDAT_data` → `png_zlib_inflate`, pngrutil.c:511)
dereferences the dangling pointer — a heap-use-after-free READ. Reachable through the
public read API on attacker-supplied PNG bytes.

## Reference crash (ASan, from discovery)

```
==ERROR: AddressSanitizer: heap-use-after-free ... READ of size 1
    #0 png_zlib_inflate         pngrutil.c:511:12
    #1 png_read_IDAT_data       pngrutil.c:4439:13
    #2 png_read_finish_IDAT     pngrutil.c:4508:7
    #3 png_read_end             pngread.c:779:7
SUMMARY: AddressSanitizer: heap-use-after-free pngrutil.c:511:12 in png_zlib_inflate
```

## Harness

`libpng_unknown_chunk_dispatch_fuzzer.cc` — libFuzzer driver over libpng's public
read API (the AGF discovery harness). Drives `png_set_keep_unknown_chunks` policy +
optional user-chunk callback from a fuzz prefix, then `png_read_info` / `png_read_end`.
The bug is reached through the public API on attacker bytes — not a hand-built invalid
internal state — so it passes the false-positive screen.
