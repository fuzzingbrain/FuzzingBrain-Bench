# systemd-hwdb-trie-oob-read — build-feasibility notes

## Build feasibility risk (FLAG)

systemd is a **large** project. Even a minimal libFuzzer build pulls in
`libsystemd-shared` plus the `libsystemd` internals, so `build-libs`
compiles a large fraction of the tree (hundreds of objects, several
minutes on a multi-core host). This is heavier than the other bench
entries (single small C lib), and is the main feasibility risk.

There is **no faithful lighter path**: the harness (`fuzz-hwdb.c`)
`#include`s systemd-internal headers (`sd-hwdb.h`, `fuzz.h`, `tests.h`,
`fd-util.h`, `fileio.h`, `tmpfile-util.h`) and calls into the
`sd-hwdb` trie objects, all of which depend on the build's generated
config (`config.h`, version files) and `basic`/`shared` static libs.
Trying to compile only "the objects the harness needs" with hand-rolled
clang would require replicating Meson's include graph and generated
headers — fragile and unfaithful — so we build through Meson via the
upstream `simple_fuzzers` machinery instead.

## How the harness is wired

`fuzz-hwdb.c` is the exact libFuzzer target upstream added in PR #42347
at `src/libsystemd/sd-hwdb/fuzz-hwdb.c`. At the **vuln_commit**
(`6f31db9b07829dcd7f166da85405eecdf889a1c8`, parent of the fix) that
file does not exist yet, but the `simple_fuzzers += files(...)` block in
`src/libsystemd/meson.build` already does. `build.sh` drops our harness
copy at the canonical path and appends it to that list, then builds with
`-Dllvm-fuzz=true`. The resulting binary is named `fuzz-hwdb`.

## Hard build dependencies

systemd hard-requires (even for fuzz builds): `libcap`, `libmount`,
`libblkid`, `libkmod`, plus `gperf` and `python3` at build time. These
are installed in the Dockerfile.

## Reproduction expectation

The shipped `poc/poc.bin` is the `regression-42340-trie-fnmatch-node-oob`
corpus file (H-1 bucket, 4209 bytes, sha256
2243ad4ceca7b571f2e950de6cfb74d822639ef3fd3a3e88e161b1c87e8c635c). On
the ASan build at the vuln_commit it reports an out-of-bounds read inside
`trie_fnmatch_f` (the `le64toh(node->prefix_off)` dereference on an
already-OOB node). Post-fix (#42347) `sd_hwdb_get` returns `-EBADMSG`
cleanly.

## NOT done here (per task scope)

No docker build, no compile, no commit. All seven files authored
faithfully; the build path is documented but unverified.
