# imagemagick-dcm-invalid-dimensions harness provenance

- **Source**: O2Lab / AGF discovery harness in
  `O2_Vulnerability_Management/projects/imagemagick/dcm-decoder-invalid-dimensions/fuzzer.cpp`
- **Upstream**: https://github.com/ImageMagick/ImageMagick/security/advisories/GHSA-8pj9-6897-74xc
- **Notes**: Uses `BlobToImage` with the `dcm:` coder (MagickCore). After decode,
  asserts every frame has non-zero `columns`/`rows` so the policy bypass becomes
  a deterministic `assert()` abort under libFuzzer.
