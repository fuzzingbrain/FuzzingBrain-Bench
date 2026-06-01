# Provenance — libheif-image-crop-overflow

- **Upstream report:** https://github.com/strukturag/libheif/issues/1746
- **Fix commit:** https://github.com/strukturag/libheif/commit/238484384bbb2fe156cf644c6433eb7570e61717
- **CVE:** none (maintainer declined — reachable only via caller-supplied crop margins; still accepted & fixed upstream)
- **vuln_commit:** `62f1b8c76ed4d8305071fdacbe74ef9717bacac5` (libheif v1.21.2) — bug PRESENT.
- **Discovery:** AGF (AI-Guided Fuzzing, Aisle Research). Reporter: Ze. Found 2026-03-21,
  submitted 2026-03-30, fixed upstream 2026-05-15.
- **Origin record:** `O2_Vulnerability_Management/agf-results/projects/oss-fuzz/libheif/heap-buffer-overflow-heif_image_crop/`

## Root cause

An integer underflow in `HeifPixelImage`'s crop path makes the crop width/height
wrap to a ~4 GB unsigned value, driving a massive out-of-bounds read during the
subsequent `memcpy`. Reachable via the public `heif_image_crop()` API, which fails
to validate the crop parameters for sub-sampled planes.

## Reference crash (this bundle's release-asan build, vuln_commit 62f1b8c)

```
==ERROR: AddressSanitizer: heap-buffer-overflow ... READ of size 4294967284
    #0 __asan_memcpy
    #1 HeifPixelImage::ImagePlane::crop(...) /src/libheif/libheif/pixelimage.cc:1313:5
    #2 HeifPixelImage::crop(...)              /src/libheif/libheif/pixelimage.cc:1289:11
    #3 heif_image_crop                        /src/libheif/libheif/api/libheif/heif_image.cc
SUMMARY: AddressSanitizer: heap-buffer-overflow ... in __asan_memcpy
```

Note: the discovery log reported `pixelimage.cc:1625` in `ImageComponent::crop`; at
the pinned vuln_commit the same routine is `ImagePlane::crop` at `pixelimage.cc:1313`.
The oracle is keyed to this bundle's actual build output.

## Harness

`image_transform_fuzzer.cc` — libFuzzer driver over libheif's public C API
(`heif_context_read_from_memory` → `heif_decode_image` → transform/crop). Last 8
input bytes are transform parameters; the rest is the HEIF stream. The crop is reached
through the public API on attacker bytes — not a hand-built invalid state — so it
passes the false-positive screen.

## Build note

libheif needs an HEVC decoder. The Dockerfile builds **libde265 v1.0.15 from source as a
static library** (uninstrumented — ASan still tracks its heap via malloc interposition;
the overflowed buffer is allocated in libheif itself) and links it statically with
`ENABLE_PLUGIN_LOADING=OFF`, so the extracted harness binary is self-contained.
