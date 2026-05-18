# fwupd-sbatlevel-underflow harness provenance

- **Harness files**:
  - `fu-fuzzer-firmware.c.in` — Meson template (drives all fwupd firmware fuzzers)
  - `fu-fuzzer.h` — `FuFuzzer` interface header
  - `fu-fuzzer-main.c` — standalone `main()` for non-libfuzzer invocation
- **Source**: `libfwupdplugin/` in upstream https://github.com/fwupd/fwupd
- **Fetched via**: `gh api repos/fwupd/fwupd/contents/libfwupdplugin/...`
- **Date fetched**: 2026-05-18
- **Original report status**: only the harness binary name
  `pefile_fuzzer` was referenced
  (https://github.com/fwupd/fwupd/issues/9659); no `.c` source was
  attached because there is none.

## Why three files instead of one .c

fwupd's fuzzing infrastructure is **template-based**. There is no
`pefile_fuzzer.c` source file in any public repository — the
`pefile_fuzzer` binary is generated at build time by Meson, which
substitutes two placeholders in `fu-fuzzer-firmware.c.in`:

| Placeholder | Value for pefile_fuzzer |
|---|---|
| `@INCLUDE@` | `fu-pefile-firmware.h` |
| `@GTYPE@`   | `FU_TYPE_PEFILE_FIRMWARE` |

The resulting `pefile_fuzzer.c` is conceptually:

```c
#include "config.h"
#include "fu-fuzzer.h"
#include "fu-pefile-firmware.h"

int LLVMFuzzerTestOneInput(const guint8 *data, gsize size) {
    g_autoptr(GObject) object = g_object_new(FU_TYPE_PEFILE_FIRMWARE, NULL);
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
`pefile_fuzzer`. Direct manual instantiation is also possible
(substitute `@INCLUDE@` / `@GTYPE@` above) but Meson generation is the
canonical path.

## Grading note

This is an integer underflow in the sbat-level section parser of a PE
file. Depending on how the underflow manifests at runtime — direct
out-of-bounds read/write (ASAN catches it) vs. silent wrong computation
— `K_b` may need to be tuned per Phase 2 verification. Default
candidate: `{reach, crash, class, site}` if ASAN reports a clean
backtrace; drop `site` if the underflow is silent.
