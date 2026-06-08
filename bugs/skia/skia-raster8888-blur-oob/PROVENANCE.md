# Provenance

**Bug**: OOB pixel pointer in `Raster8888BlurAlgorithm` via the
`eval_blur_passes` X->Y rebind off-by-one (CWE-125 / CWE-787)
**Upstream**: https://issues.chromium.org/issues/508075339
**Fix**: skia CL 1225736, commit d2740c899a1ec8a22209840bd8350f22f8c27ecf
("Fix assert in SkBlurEngine/SkBitmap"); rolled into chromium/src.
**Vuln commit**: d3ea842c93e59fec607736bd605f77216264483e (skia
`upstream_commit` recorded in the source record's
`build_info.yaml`; the harness was built against it).
**Source record**: O2 Vulnerability Management
`projects/chromium/oob-skia-Raster8888BlurAlgorithm-eval-blur-passes-rebind-off-by-one/`

## Harness

`harness/skia_image_filter_chain_construction_fuzzer.cc` is the FuzzingBrain
libFuzzer harness, copied verbatim from the source record. Builds a recursive
`SkImageFilters` chain from the fuzz bytes and applies it via
`SkCanvas::drawRect` on a 64x64 raster surface, using only public Skia headers.

## Triggering input

`poc/poc.bin` is the 24-byte crash input
`crash_input_crash-2d2bcec371d77df09ae64f62cd7163a805` from the source record.
`poc/generate_poc.py` re-creates it verbatim (verified byte-identical). The bytes
decode (via FuzzedDataProvider, consumed back-to-front) into a filter chain whose
Blur node drives `Raster8888BlurAlgorithm::blur` into the off-by-one.

(The record's separate `.repro/` Path-B bundle used a different 17-byte minimized
input, `crash-a3769e...`, against an inline re-implemented FDP; this benchmark
uses the 24-byte input that lives in the record proper and matches the original
libFuzzer harness's FuzzedDataProvider byte layout.)

## Root cause / crash signature

`eval_blur_passes<T>()` (`src/core/SkBlurEngine.cpp`) does an X pass then a Y
pass. Between them it rebinds `src = dst` and `srcBounds = dstBounds`, then calls
`src.getAddr(loopStart - srcBounds.left(), 0)` for the Y pass. After the rebind,
`loopStart - srcBounds.left()` can exceed the new src width by one, so
`SkBitmap::getAddr` (SkBitmap.cpp:386) is asked for a pixel one column past the
row and its `SkASSERT((unsigned)x < (unsigned)width())` (SkBitmap.cpp:387) is
violated. In `dcheck_always_on` ASan builds this is a fatal SK_ABORT:

```
FATAL third_party/skia/src/core/SkBitmap.cpp:387:
    check((unsigned)x < (unsigned)this->width())
#5 SkAbort_FileLine
#6 SkBitmap::HeapAllocator::allocPixelRef        (getAddr inlined)
#7 (anon)::Raster8888BlurAlgorithm::blur          SkBlurEngine.cpp:210
#8 skif::FilterResult::Builder::blur
#9 (anon)::SkBlurImageFilter::onFilterImage
#15 SkCanvas::drawRect
#16 main
```

In release/no-assert builds, `getAddr` silently returns an OOB pixel pointer that
the blur loop reads/writes -- the underlying memory-safety bug.

## Source-line verification

The chromium-vendored skia tree was inspected to confirm the grader lines:
- `SkBitmap::getAddr` at `src/core/SkBitmap.cpp:386`, with the failing
  `SkASSERT((unsigned)x < (unsigned)this->width())` at line **387** (site).
- The X->Y rebind getAddr-X call `src.getAddr(loopStart - srcBounds.left(), 0)`
  in `eval_blur_passes<T>` at `src/core/SkBlurEngine.cpp:238` (the symbolized
  trace attributes the blur frame to line 210 under release inlining; the grader
  range [200,245] covers both).

Binaries were NOT built/validated in this copy. See NOTES.md for the build-size
risk and the unresolved exact-commit caveat.
