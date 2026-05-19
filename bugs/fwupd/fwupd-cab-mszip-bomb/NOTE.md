# fwupd-cab-mszip-bomb — partial build infra, deferred

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
