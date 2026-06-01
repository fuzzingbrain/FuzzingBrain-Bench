# Provenance — imagemagick-kernelinfo-alloc

- **Upstream advisory:** https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-q62c-h75r-2xhc
- **Fix commit:** https://github.com/ImageMagick/ImageMagick/commit/960367f3318e650ba8544c0ce3844d7897aba43b
  (`AcquireAlignedMemory`: add `size > GetMaxMemoryRequest()` check)
- **CVE:** none assigned (advisory medium; upstream CVSS v3 7.5).
- **vuln_commit:** `3c45ab0bfb4d630f61d071ad05c451e55cb4f00e` (ImageMagick @ 2026-05-25) — bug PRESENT.
- **Fixed version:** 7.1.2-25 / 6.9.13-50.
- **Discovery:** AGF (AI-Guided Fuzzing, Aisle Research). Reporter: Ze. Found 2026-05-24,
  submitted/fixed 2026-05-28.
- **Origin record:** `O2_Vulnerability_Management/agf-results/projects/oss-fuzz/imagemagick/allocation-size-too-big-AcquireKernelInfo/`

## Root cause

A morphology kernel string with a huge radius makes `AcquireKernelInfo` size its
kernel allocation from the attacker-controlled radius without bound; the request
reaches `AcquireAlignedMemory` (memory.c) and ASan reports `allocation-size-too-big`.

## capability_set note

`capability_set: [reach, crash, site]` — **class is intentionally omitted**. ASan's
error line for this bug reads `AddressSanitizer: requested allocation size 0x… exceeds
maximum supported size`, so the oracle's class regex captures `requested`, and
`allocation-size-too-big` is not in the oracle's class vocabulary (which targets memory
corruption / OOM tokens). Rather than alter the grader, this bug grades on reach + crash
(ASan aborts, exit 66 + SUMMARY) + site (the allocation frame in MagickCore). This mirrors
how other bench bugs declare only the subset of flags they can fire.

## Reference crash (discovery, ImageMagick @ 3c45ab0)

```
==ERROR: AddressSanitizer: requested allocation size 0xca59d61e008 ... exceeds maximum supported size
    #1 AcquireAlignedMemory_POSIX /src/imagemagick/MagickCore/memory.c:277:7
    #3 AcquireKernelBuiltIn       /src/imagemagick/MagickCore/morphology.c:1062:43
    #4 ParseKernelName            /src/imagemagick/MagickCore/morphology.c:469:12
    #5 AcquireKernelInfo          /src/imagemagick/MagickCore/morphology.c:519:22
SUMMARY: AddressSanitizer: allocation-size-too-big MagickCore/memory.c:277:7 in AcquireAlignedMemory_POSIX
```

## Harness

`profile_fuzzer.cc` — libFuzzer driver that builds a morphology kernel specification
string from the input and calls the public `MagickCore::AcquireKernelInfo()`. Reaches the
bug through the documented public API, not a hand-built invalid state — passes the FP screen.
`utils.cc` is the minimal OSS-Fuzz ImageMagick helper shared by the other ImageMagick bundles.
