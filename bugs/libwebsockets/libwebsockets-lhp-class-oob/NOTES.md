# Notes / provenance — libwebsockets-lhp-class-oob

## Source record
`O2_Vulnerability_Management/projects/libwebsockets/heap-buffer-overflow-lhp_element_has_class-via-lws_lhp_parse/`

- Disclosure: private email to andy@warmcat.com per libwebsockets SECURITY.md.
- Fix commit: `bd57edb5fc` ("lhp: heap buffer overflow. Aisle Research reported...").
- Discoverer: AGF (O2Lab).

## Harness — PRESENT, copied verbatim
Copied byte-for-byte from the record's `lws_upng_inflate_fuzzer.cpp` and renamed
to `harness/lws_lhp_fuzzer.cc` (the record filename is a misnomer — the file is the
LHP parse fuzzer, not a upng/inflate fuzzer). Contents are unchanged. It is a
libFuzzer harness that builds an lhp context with a display-list renderer and feeds
input bytes into lws_lhp_parse, then a document-end flush. It contains a
`neutralize_external_fetch_keywords()` mutation (src/href/url/background -> x) to
keep the parser from crossing the network-fetch boundary; the record confirms the
bug reproduces independently of this neutralization (clean minimal PoC with no such
keywords).

## PoC — PRESENT, copied verbatim
`poc/poc.bin` is the record's `crash_input` (774 bytes).

## vuln_commit — DERIVED (gap / mirror mismatch)
The record states the bug is "present on master (c043c36, 2026-05-30)". The short
hash `c043c36` does NOT resolve on the public github.com/warmcat/libwebsockets
mirror (it appears to be a hash from the reporter's local clone/branch state, not a
public master commit). I instead pinned the **parent of the public fix** `bd57edb5fc`:
  vuln_commit = 8a422a736b84191a2fd4ec492d82888096329817 (2026-05-29, bug PRESENT)
This is the faithful pre-fix master state immediately before the lhp fix, consistent
with the record's "master, 2026-05-30" timeframe.

## Grader site
ASan trace (asan_apitest_lhp.txt / asan_min_app.txt / vuln.yaml crash_signature):
  #0 strlen ; #1 lhp_element_has_class lib/misc/lhp.c:824:11  (READ size 2, 0 bytes
     after a 47-byte region)
Faulting library frame = lhp_element_has_class @ lhp.c:824; strlen is the asan
interceptor leaf at frame 0 (so the site is at frame distance 1).

## Build notes
libwebsockets builds with CMake. Static, instrumented, with LHP + DLO + secure
streams enabled (all default ON) and SSL/test-apps disabled so the harness binary
is self-contained. libcap is linked because lws references it in default builds
(libcap-dev installed in the Dockerfile).

## NOT done (per task scope)
No docker build, no compile, no commit. build.sh/Dockerfile are unverified by
execution.
