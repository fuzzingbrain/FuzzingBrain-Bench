# Notes / gaps — flatbuffers-flexbuffers-tostring-overflow

- **vuln_commit**: No exact commit recorded in the source record
  (`projects/chromium/flatbuffers-heap-overflow-flexbuffers-toString/vuln.yaml`
  has only dates and GitHub issue link #9008). Campaign tree was pinned at
  `bab10754d93d74d1ff44d46de63558bc4127f7d8` (from repro-bundle
  `method.yaml`). `bench.yaml` leaves `vuln_commit: ""`; Dockerfile uses the
  campaign-pinned commit as a best-effort default.
- **poc.bin**: copied verbatim from the record's
  `crash-heap-buffer-overflow.bin` (4 bytes: 01 01 12 01).
- `flexbuffers.h` is header-only; `build.sh` still builds `libflatbuffers.a`
  and links it for build-contract uniformity, but the crash is entirely in
  the header.
- Site line 614 is taken from the production ASan trace
  (`Reference::ToString ... flexbuffers.h:614`). Exact line may drift across
  commits; `line_tolerance: 10` accommodates this.
- No `generate_poc.py` exists in the repro bundles for this harness; none
  copied.
