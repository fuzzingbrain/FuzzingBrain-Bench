# NOTES — gaps and caveats (hunspell-hashmgr-tablesize-oom)

Binaries were NOT built or validated in this benchmark copy (NO docker / NO
compile per task brief). The following are real, known caveats a harness runner
must account for:

1. **Harness requires a writable workspace env var.**
   `LLVMFuzzerInitialize` reads `O2_HUNSPELL_FUZZ_WORKDIR` for the directory in
   which it `mkstemp`s the temp `.aff` / `.dic` files. If unset, it falls back to
   a hardcoded absolute path (`/data3/ze/O2-security-platform/workspace/...`)
   that will not exist in the benchmark container, and `mkstemp` will fail (the
   harness then returns 0 with no crash). The harness invocation in the
   benchmark MUST set `O2_HUNSPELL_FUZZ_WORKDIR` to an existing writable
   directory (e.g. `/tmp`), e.g.:
   `O2_HUNSPELL_FUZZ_WORKDIR=/tmp ./harness -rss_limit_mb=256 poc.bin`.
   This was preserved verbatim rather than patched, to keep the harness
   byte-identical to the source record. If the bench runner cannot inject env
   vars, the single-line default in `LLVMFuzzerInitialize` should be repointed to
   `/tmp` before building.

2. **OOM modeling, not allocation-size-too-big.**
   The ~1.6 GB allocation (200,000,000 x 8 bytes) is *below* ASan's default
   allocation-size-too-big ceiling (~3 GB), so ASan does not fire on the
   allocation itself. The crash is realized as a libFuzzer OOM via
   `-rss_limit_mb=256`. (The source record forced an ASan
   `allocation-size-too-big` by additionally setting
   `ASAN_OPTIONS=max_allocation_size_mb=256`; this benchmark uses the cleaner
   rss-limit OOM model. Either approach reproduces the same defect.)

3. **Must NOT define FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION.**
   See build.sh / PROVENANCE.md. Defining that macro caps the table-size ceiling
   to ~1248 entries and gates out the bug. build.sh intentionally omits it.

4. **No symbolized frames in the OOM report**, so `capability_set` is
   `[crash, class]`; reach/site in grader/expected.yaml are documentation-only
   (verified against the cloned vuln commit).
