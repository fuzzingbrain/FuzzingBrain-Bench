# systemd-hwdb-trie-oob-read harness provenance

- **Source**: `fuzz-hwdb.c` is the exact libFuzzer target added by merged
  PR https://github.com/systemd/systemd/pull/42347 at
  `src/libsystemd/sd-hwdb/fuzz-hwdb.c`.
- **Found in**: PR #42347 (merge commit
  73fea38cf1344e08213bb10bfc1e1a98382aee78). Copied **verbatim** from the
  vuln-mgmt record
  `projects/systemd/hwdb-trie-oob-read/fuzz-hwdb.c`.
- **Behavior**: writes the fuzzer bytes to a temp file, maps it via
  `sd_hwdb_new_from_path`, then drives `sd_hwdb_get` (→ `trie_search_f` /
  `trie_fnmatch_f`) and `sd_hwdb_seek` + `sd_hwdb_enumerate` (capped at
  `MAX_ENUMERATE=1024` to bound offset-cycle loops) over a fixed set of
  modaliases.
- **Notes**: the harness is the upstream fixture; the *bug* lives in the
  pre-fix `src/libsystemd/sd-hwdb/sd-hwdb.c` at the vuln_commit
  (6f31db9b07829dcd7f166da85405eecdf889a1c8).
