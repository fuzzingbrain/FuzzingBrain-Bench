#!/bin/bash
# Build one d8 config for the v8 target and assemble a self-contained harness dir.
# Produces /out/<config>/harness (a wrapper) beside d8 + snapshot_blob.bin + icudtl.dat.
#
# Unlike the C/C++ targets (a single clang invocation), V8 must be built with its
# own toolchain (depot_tools + gn + autoninja). The source tree at /src/v8 is
# expected to already be checked out at the desired commit — the Dockerfile pins
# the vuln commit for the release-asan slot and the fix commit for the fixed-asan
# slot, then invokes this script once per slot.
set -euo pipefail
CONFIG="${1:?usage: build.sh <config>   (release-asan | fixed-asan | coverage)}"
V8=/src/v8
OUT=/out/${CONFIG}
GNDIR=out/${CONFIG}

# The 'release-asan' / 'fixed-asan' slot names are the oracle's fixed
# directory conventions, independent of what this particular build links in.
cd "${V8}"
mkdir -p "${GNDIR}"
cat > "${GNDIR}/args.gn" <<'GN'
is_debug = false
dcheck_always_on = true
v8_static_library = true
v8_enable_verify_heap = true
v8_enable_partition_alloc = false
target_cpu = "x64"
use_remoteexec = false
GN
gn gen "${GNDIR}"
autoninja -C "${GNDIR}" d8

mkdir -p "${OUT}"
cp "${GNDIR}/d8"                "${OUT}/d8"
cp "${GNDIR}/snapshot_blob.bin" "${OUT}/snapshot_blob.bin"
cp "${GNDIR}/icudtl.dat"        "${OUT}/icudtl.dat"
install -m 0755 /src/harness/run-d8 "${OUT}/harness"
echo "built ${OUT}/harness (d8 $(stat -c %s "${OUT}/d8") bytes)"
