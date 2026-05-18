# binutils-rust-demangle-oom harness provenance

- **Source**: Sourceware Bugzilla 33878 itself is Anubis-gated and could not be fetched. The Ghidra advisory GHSA-m94m-fqr3-x442 (https://github.com/NationalSecurityAgency/ghidra/security/advisories/GHSA-m94m-fqr3-x442) covers the same bug and notes "To track the issue in `binutils`, see https://sourceware.org/bugzilla/show_bug.cgi?id=33878"; the harness shown there (fuzz_rust_demangle.c) targets `libiberty/rust-demangle.c`, which is shared between binutils and Ghidra's bundled GPL DemanglerGnu copy.
- **URL fragment**: cross-referenced from GHSA-m94m-fqr3-x442
- **Found in**: linked advisory (sibling bug)
- **Notes**: Bugzilla page itself blocked by Anubis (per upstream caveat in bench-corpus.json). Same harness as the two Ghidra entries since the underlying rust-demangle.c source is shared.
