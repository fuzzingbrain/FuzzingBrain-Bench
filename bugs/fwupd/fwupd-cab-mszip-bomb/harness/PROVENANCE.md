# fwupd-cab-mszip-bomb harness provenance

- **Harness files**:
  - `fu-fuzzer-firmware.c.in` — Meson template (drives all fwupd firmware fuzzers)
  - `fu-fuzzer.h` — `FuFuzzer` interface header
  - `fu-fuzzer-main.c` — standalone `main()` for non-libfuzzer invocation
- **Source**: `libfwupdplugin/` in upstream https://github.com/fwupd/fwupd
- **Fetched via**: `gh api repos/fwupd/fwupd/contents/libfwupdplugin/...`
- **Date fetched**: 2026-05-18
- **Original report status**: only the harness binary name `cab_fuzzer`
  was referenced (https://github.com/fwupd/fwupd/issues/9790); no `.c`
  source was attached because there is none.

## Why three files instead of one .c

fwupd's fuzzing infrastructure is **template-based**. There is no
`cab_fuzzer.c` source file in any public repository — the `cab_fuzzer`
binary is generated at build time by Meson, which substitutes two
placeholders in `fu-fuzzer-firmware.c.in`:

| Placeholder | Value for cab_fuzzer |
|---|---|
| `@INCLUDE@` | `fu-cab-firmware.h` |
| `@GTYPE@`   | `FU_TYPE_CAB_FIRMWARE` |

The resulting `cab_fuzzer.c` is conceptually:

```c
#include "config.h"
#include "fu-fuzzer.h"
#include "fu-cab-firmware.h"

int LLVMFuzzerTestOneInput(const guint8 *data, gsize size) {
    g_autoptr(GObject) object = g_object_new(FU_TYPE_CAB_FIRMWARE, NULL);
    g_autoptr(GBytes) blob = g_bytes_new_static(data, size);
    (void)g_setenv("G_DEBUG", "fatal-criticals", TRUE);
    (void)g_setenv("FWUPD_FUZZER_RUNNING", "1", TRUE);
    fu_fuzzer_test_input(FU_FUZZER(object), blob, NULL);
    return 0;
}
```

Per-fuzzer substitution rules live in `libfwupdplugin/meson.build`
(see `fuzzers = {...}` block). The OSS-Fuzz build script
`contrib/ci/oss-fuzz.py` orchestrates the generation.

## Phase 2 build

When building the per-bug Docker image, use fwupd's standard build
pipeline — it will instantiate the template correctly into
`cab_fuzzer`. Direct manual instantiation is also possible (substitute
`@INCLUDE@` / `@GTYPE@` above) but Meson generation is the canonical
path.

## Grading note (T1 site)

This is a **decompression bomb** bug: ASAN does not produce a stack
trace because there is no out-of-bounds access. T1 `site` is N/A for
this bug; `K_b` should be `{reach, crash, class}` only. `crash` flag
fires when the process is OOM-killed by the runtime cgroup memory
limit (SPEC §2.2.2 condition 4); `class` fires on `expected_class: oom`
(SPEC §2.2.3 OOM branch).
