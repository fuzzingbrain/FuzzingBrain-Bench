# Notes / provenance — openh264-scenechange-overflow

## Source record
`O2_Vulnerability_Management/projects/iot-targets/openh264/heap-overflow-scenechangedetection/`

- Upstream: https://github.com/cisco/openh264/issues/3926 (confirmed by maintainer)
- Discoverer: O2Lab Fuzzing Team.

## Harness — PRESENT, copied verbatim
`harness/processing_fuzzer.cpp` is copied byte-for-byte from the record. It is a
libFuzzer harness (LLVMFuzzerTestOneInput) over the public IWelsVP video-processing
API: WelsCreateVpInterface -> Init(method) -> Process(SPixMap). It parses the first
5 input bytes as {method, width, height} and drives the selected processing method.

## PoC — PRESENT, copied verbatim
`poc/poc.bin` is the record's `crash_input.bin` (1541 bytes on disk).
NOTE: VERIFY.md prose says "PoC input (315 bytes)", but the actual
`crash_input.bin` in the record is 1541 bytes — the real file was copied verbatim;
the 315 figure in the record's prose is stale/inconsistent.

## vuln_commit — DERIVED (gap in record)
The record's vuln.yaml says only `affected_versions: "latest (commit at 2026-01-27)"`
with no SHA. The cisco/openh264 master HEAD as of 2026-01-27 is
  vuln_commit = cf568c83f71a18778f9a16e344effaf40c11b752 (2025-10-28, last activity before disclosure)
which is the repo state the record's "latest" refers to. No fix commit is recorded
(maintainer was "preparing PR" at disclosure time; vuln.yaml fix.commit is empty), so
the fix-parent technique used for the other two bugs is not available here.

## Grader site
ASan trace (vuln.yaml / VERIFY.md):
  #0 WelsSampleSad8x8_c codec/common/src/sad_common.cpp:82  (READ size 1, 0 bytes
     past an 864-byte region)
Faulting frame = WelsSampleSad8x8_c @ sad_common.cpp:82.

## Build notes
OpenH264 builds with its own GNU make. `make libraries` produces the combined
static archive `libopenh264.a` containing the common + processing module objects.
Built C-only (`USE_ASM=No`) so the C reference SAD kernel WelsSampleSad8x8_c (the
exact `_c` function in the trace) runs instead of a hand-asm variant, letting ASan
observe the OOB read. Builds in-tree, so a per-config source copy is used.

NOTE: the record's verify build compiled the harness with a separate
`fuzzer_main.cpp` (standalone driver). Here the entry is built as a proper
libFuzzer harness (`-fsanitize=fuzzer`), matching the other bench entries; no
hand-rolled main is needed and none was fabricated.

## NOT done (per task scope)
No docker build, no compile, no commit. build.sh/Dockerfile are unverified by
execution.
