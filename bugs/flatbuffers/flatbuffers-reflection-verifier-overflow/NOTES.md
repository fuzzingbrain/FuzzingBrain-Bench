# Notes / gaps — flatbuffers-reflection-verifier-overflow

- **vuln_commit**: `e223d69b36574c4a2b10dbd27761753de81624ab` — taken from the
  GetField-variant bug report
  (`bug_reports/.../heap-overflow-flatbuffers-reflection-verifier-GetField.md`),
  which states `git checkout e223d69b36574c4a2b10dbd27761753de81624ab` and
  "Affected Versions: commit e223d69b... (main branch, 2026-04-13)". The
  campaign repro tree was pinned at
  `bab10754d93d74d1ff44d46de63558bc4127f7d8` and is documented to reproduce
  the identical crash with unchanged line numbers; either commit works.
- **harness source**: copied verbatim from the record dir
  (`flatbuffers_reflection_gentext_fuzzer.cc`). NOTE: the matching report
  `heap-overflow-flatbuffers-reflection-verifier.md` embeds a *different*,
  simplified harness listing under "Fuzz Harness Source"; the record's
  actual `.cc` (the one used) loads `monster_test.bfbs` via
  LLVMFuzzerInitialize and calls `flatbuffers::Verify(schema, root_def, ...)`.
  The ASan trace in that report (`#5 ... flatbuffers_reflection_gentext_fuzzer.cc:110`)
  matches the record's `.cc`, so the record harness is authoritative.
- **runtime data dependency**: this harness loads `monster_test.bfbs` from
  the directory of the executable. `build.sh` generates it with the freshly
  built `flatc` from `tests/monster_test.fbs` and copies it next to each
  harness in `/out/<config>/`. If verification needs additional include
  schemas, the `-I tests/include_test` flag in build.sh covers
  `tests/include_test/*.fbs`. NOT compiled/verified here.
- **poc.bin**: copied verbatim from the record's crash artifact
  `crash_input_crash-3be5d6a5db6d53bc14fe9e8a78d0fb1297` (600 bytes). NOTE:
  the report's inline Python PoC generates a different 243-byte input; the
  ASan trace's "243-byte region" matches that report-PoC size, while the
  record's persisted crash artifact is 600 bytes. The 600-byte record
  artifact is used as poc.bin since it is the real persisted crash input;
  both exercise the same VerifyObject -> GetFieldT -> ReadScalar path.
- No `generate_poc.py` exists in the repro bundles for this harness; none
  copied.
- **site** keyed to `base.h:428` (the ReadScalar OOB read, ASan frame #0).
  Reach keyed to `VerifyObject` (the reflection verifier driver).
