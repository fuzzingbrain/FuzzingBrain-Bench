# skia-raster8888-blur-oob harness provenance

- **Source**: O2 Vulnerability Management record
  `projects/chromium/oob-skia-Raster8888BlurAlgorithm-eval-blur-passes-rebind-off-by-one/skia_image_filter_chain_construction_fuzzer.cc`
  (discovered by O2 Security Team / FuzzingBrain, Chrome maintenance fuzzing
  campaign, 2026-04-24). Copied verbatim, byte-for-byte.
- **Found in**: O2 internal `data/chrome/libraries/skia/harnesses/`
- **Notes**: libFuzzer harness. `MakeRandomFilter` recursively builds an
  `SkImageFilters` chain from the fuzz input (Blur / Compose / Offset /
  DropShadow / Crop / Merge / MatrixTransform / Empty; max depth 16), sets it as
  the image filter on an `SkPaint`, and calls `SkCanvas::drawRect` on a 64x64
  N32Premul raster surface. The Blur node (sigmaX/sigmaY each in [0,100]) drives
  the software `Raster8888BlurAlgorithm::blur` path. Uses only public Skia
  headers (`include/core/`, `include/effects/`). The harness build was
  originally `chromium-gn-ninja` against skia `upstream_commit
  d3ea842c93e59fec607736bd605f77216264483e` (per the record's build_info.yaml).
