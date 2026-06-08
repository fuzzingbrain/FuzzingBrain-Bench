# systemd-pe-binary-dos harness provenance

- **Source**: `fuzz-pe-binary.c` is the exact libFuzzer target added by
  merged PR https://github.com/systemd/systemd/pull/42348 at
  `src/fuzz/fuzz-pe-binary.c`.
- **Found in**: PR #42348 (merge commit
  0c5cba64209db554077dfe12c5f1f3b1c547f666). Copied **verbatim** from the
  vuln-mgmt record
  `projects/systemd/pe-binary-algocomplexity-dos/fuzz-pe-binary.c`.
- **Behavior**: wraps the fuzzer bytes in a memfd, runs `pe_load_headers`
  / `pe_load_sections`, reads each UKI section via
  `pe_read_section_data_by_name` (capped at `FUZZ_SECTION_READ_MAX`), then
  — when OpenSSL is available — calls `uki_hash()`, which contains the
  attacker-amplifiable zero-padding hash loop that this entry targets.
- **Notes**: the harness is the upstream fixture added *with* the fix; the
  *bug* lives in the pre-fix `src/shared/pe-binary.c` (`uki_hash`) at the
  vuln_commit (97a0ec135b1a3330abe8c34794c6e31b266452fc). Because the
  upstream harness did not exist before the fix, `build.sh` creates it at
  the canonical path and registers it in `src/fuzz/meson.build`.
