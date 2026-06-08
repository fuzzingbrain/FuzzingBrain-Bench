# Provenance

**Bug**: Unbounded heap allocation (~1.6 GB) in `HashMgr::load_tables` via an
unvalidated `tablesize` field in a `.dic` file (CWE-789 / CWE-1284)
**Upstream**: https://github.com/hunspell/hunspell/issues/1116
**Vuln commit**: f23fcd33052c7c8a307eaa3e1b1a4c0cdcf45651
**Source record**: O2 Vulnerability Management
`projects/chromium/dos-hunspell-hashmgr-tablesize-unbounded-alloc/`

## Harness

`harness/hunspell_hashmgr_dic_loader_fuzzer.cc` is the FuzzingBrain libFuzzer
harness, copied verbatim from the source record. It drives the `Hunspell(aff,
dic)` ctor (→ `HashMgr::load_tables`), `add_dic()`, and `spell()` over
fuzz-controlled temp `.aff` / `.dic` files.

## Build

`build.sh` builds libhunspell with autotools (autoreconf + out-of-tree
`configure --disable-shared --enable-static --without-readline`) under two
sanitizer flavors (asan, cov) and links the harness against
`libhunspell-1.7.a`. The build deliberately does NOT define
`FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION` — that macro caps `max_allowed` to
~1248 entries inside `load_tables` and would gate out the bug; production builds
get the full `INT_MAX/sizeof(hentry*)` ceiling that lets the 200,000,000-entry
header through to the unbounded `resize()`.

## Triggering input

`poc/poc.bin` is the 16-byte minimized PoC `.dic` from the source record's
verified `.repro/` bundle: the literal ASCII `"200000000\nhello\n"`. The first
line claims 200,000,000 entries; the file contains exactly one. `load_tables`
trusts line 1 and pre-resizes the hash table to ~200M slots x 8 bytes ≈ 1.6 GB
before reading the second line. `poc/generate_poc.py` re-creates it verbatim.

## Crash signature / classification

Modeled as a libFuzzer out-of-memory. The ~1.6 GB request is below ASan's
default allocation-size-too-big ceiling, so it is surfaced via
`-rss_limit_mb=256`:

```
==PID== ERROR: libFuzzer: out-of-memory (used: ...Mb; limit: 256Mb)
SUMMARY: libFuzzer: out-of-memory
```

The rss-based OOM banner carries no symbolized frames and coverage cannot flush
before the OOM kill, so only `crash` + `class` are machine-gradable
(`capability_set: [crash, class]`). `expected.yaml` grades `class: oom` and
records reach/site (`hashmgr.cxx` `load_tables` / line 642) for documentation.

## Verification status (in this benchmark copy)

Source-line locations were verified by cloning hunspell at the vuln commit:
`load_tables` at hashmgr.cxx:602, the unbounded `tableptr.resize(tablesize,
nullptr)` at line 642, `HashMgr::HashMgr` ctor at line 88 (grader frame 6).
Binaries were NOT built/validated in this copy (NO docker / NO compile per task
brief). See NOTES.md for the one runtime caveat (harness workdir env var).
