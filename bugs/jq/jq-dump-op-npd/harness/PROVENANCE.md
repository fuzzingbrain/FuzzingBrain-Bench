# jq-dump-op-npd harness provenance

- **Harness file**: `jq_fuzz_compile.c`
- **Source**: `tests/jq_fuzz_compile.c` in upstream https://github.com/jqlang/jq
- **Fetched via**: `gh api repos/jqlang/jq/contents/tests/jq_fuzz_compile.c`
- **Date fetched**: 2026-05-18

This is the upstream OSS-Fuzz harness for jq's compile path. The bug's
report (https://github.com/jqlang/jq/issues/3458) references "the OSS-Fuzz
jq fuzzer" by name without pasting source; this harness is built by
OSS-Fuzz's `projects/jq/build.sh` and is the standard fuzz target for
the `dump_operation` code path.

The issue also provides a CLI reproducer (`jq --debug-dump-disasm -n -f
poc.jq`) and a Python generator for the trigger input — those drive the
jq CLI binary; the harness above drives the libfuzzer entrypoint
against the same compile path.
