# Notes / gaps — flatbuffers-flexbuffers-tostring-overflow

- **vuln_commit**: No exact commit recorded in the source record
  (`projects/chromium/flatbuffers-heap-overflow-flexbuffers-toString/vuln.yaml`
  has only dates and GitHub issue link #9008). Campaign tree was pinned at
  `bab10754d93d74d1ff44d46de63558bc4127f7d8` (from repro-bundle
  `method.yaml`). `bench.yaml` now pins that campaign tree as `vuln_commit`
  (matching the Dockerfile/binary build), so the source stages and grades
  consistently; it is the campaign-pinned vulnerable snapshot, not a
  precisely-bisected introducing commit.
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
