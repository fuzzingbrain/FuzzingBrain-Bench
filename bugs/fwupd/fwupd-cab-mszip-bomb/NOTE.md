# fwupd-cab-mszip-bomb — coverage build resolved (2026-06-11)

UPDATE 2026-06-11 — the build is NOT infeasible; the 2026-05-19 blockers below
were the wrong options + an over-broad dep set. The coverage binary was built
and reach is now graded ([crash, class] -> [class, crash, reach]). Recipe:

1. The unknown-option errors (`plugin_uefi_capsule` etc.) are just stale option
   names — DROP them. fwupd 2.0.18 configures fine on the system deps already
   present (glib, gio, json-glib, xmlb/jcat subprojects, gusb, gnutls, libcurl);
   the `.gir` introspection targets fail under Python 3.12 but are irrelevant —
   `ninja -k0` still produces libfwupdplugin.a + libfwupd.a.
2. `meson compile cab_fuzzer` does NOT work on 2.0.18 — the fuzzers are built by
   `contrib/ci/oss-fuzz.py`, not a meson target. Instead: generate the fuzzer
   from `libfwupdplugin/fu-fuzzer-firmware.c.in` (@INCLUDE@=fu-cab-firmware.h,
   @FIRMWARENEW@=g_object_new(FU_TYPE_CAB_FIRMWARE, NULL)) and hand-link it
   against the static libs + system deps (-lcbor -lz -lzstd -llzma).
3. OOM coverage: the unit is OOM-killed before atexit, so the cov binary is
   built with -fprofile-instr-generate -fcoverage-mapping -fprofile-continuous
   and the grader runs it with the %c profile marker (counters mmap'd live) ->
   the MSZIP decompression coverage in fu-cab-firmware.c survives the kill.
   Opt-in is explicit: expected.yaml `reach.coverage_continuous: true`.

The 2026-05-19 deferral notes are kept below for history (the daemon/tool build
is still heavy; only the cab_fuzzer + libfwupdplugin path is needed here).

---

Build attempt status (2026-05-19):

After resolving many transitive dependencies (gobject-introspection,
gtk-doc-tools, libgpgme, gnutls-bin, python3-jinja2, python3-cairo,
python3-gi), `meson setup` for fwupd 2.0.18 still fails because:

1. fwupd 2.0.18's `meson_options.txt` no longer carries the
   `plugin_uefi_capsule` / `plugin_thunderbolt` / `plugin_redfish`
   options that older versions accepted, so we can't disable those
   plugins individually.
2. The default build pulls in pango, pangocairo, drm_amdgpu, umockdev,
   flashrom, and other system libs that aren't in our minimal apt set.

The fwupd `contrib/ci/oss-fuzz.py` script is the canonical path: it
clones source for glib, json-glib, libxmlb, libjcat at pinned commits
and builds everything from scratch. That works but costs ~30 min per
fresh build and ~10 GB of disk per image — out of scope for v1.

**Promotion path**:
- Vendor `oss-fuzz.py` directly into the Dockerfile, or
- Pin fwupd to a slightly older version with simpler meson options, or
- Apt-install pango/drm/umockdev/etc. and accept the larger image.

The libfwupdplugin template fuzzer (`fu-fuzzer-firmware.c.in`) +
fwupd's own meson custom_target machinery would then produce
`cab_fuzzer` automatically; harness/build.sh's `meson compile -j N
cab_fuzzer` is correct as-is.

The other three fwupd bugs (logitech-oob-read, logitech-stack-overflow,
sbatlevel-underflow) share the same blocker.
