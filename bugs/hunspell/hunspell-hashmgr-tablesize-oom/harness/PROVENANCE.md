# hunspell-hashmgr-tablesize-oom harness provenance

- **Source**: O2 Vulnerability Management record
  `projects/chromium/dos-hunspell-hashmgr-tablesize-unbounded-alloc/hunspell_hashmgr_dic_loader_fuzzer.cc`
  (discovered by O2 Security Team / FuzzingBrain, Chrome maintenance fuzzing
  campaign, 2026-04-14). Copied verbatim, byte-for-byte.
- **Found in**: O2 internal `data/chrome/libraries/hunspell/harnesses/`
- **Notes**: libFuzzer harness. Per iteration it slices the fuzz input into an
  AF/AM alias block, a primary `.dic`, an optional custom `.dic`, and trailing
  word bytes, writes them to temp files under a workspace directory, constructs
  `Hunspell(aff, dic)` (which calls `HashMgr::load_tables`), optionally
  `add_dic()`s the custom dictionary, and `spell()`s a few words. The primary
  `.dic` body is the slice that carries the attacker-controlled first-line word
  count reaching the unbounded `resize()`.
