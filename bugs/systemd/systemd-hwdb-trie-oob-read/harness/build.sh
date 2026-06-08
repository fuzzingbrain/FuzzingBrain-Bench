#!/bin/bash
# Build for systemd-hwdb-trie-oob-read.
#
# systemd uses the Meson build system. The libFuzzer harness fuzz-hwdb.c
# uses systemd-internal headers (sd-hwdb.h, fuzz.h, tests.h, ...) and must
# be linked against libsystemd internals, so it is built *through* Meson via
# the existing `simple_fuzzers` machinery rather than hand-rolled with clang.
#
# Our harness copy is dropped into the tree at the canonical upstream path
# (src/libsystemd/sd-hwdb/fuzz-hwdb.c) and appended to the simple_fuzzers
# list in src/libsystemd/meson.build. Meson with -Dllvm-fuzz=true then emits
# a libFuzzer binary named `fuzz-hwdb` in the build directory.
#
# NOTE (build feasibility): this compiles a large fraction of systemd
# (libsystemd-shared + libsystemd internals). It is heavy but bounded; see
# NOTES.md. There is no lighter faithful path because the harness pulls in
# fuzz.h / tests.h / the sd-hwdb objects.
set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"
SRC=/src/systemd
HARNESS_DST="${SRC}/src/libsystemd/sd-hwdb/fuzz-hwdb.c"
MESON_FILE="${SRC}/src/libsystemd/meson.build"

install_harness() {
    cp /src/harness/fuzz-hwdb.c "${HARNESS_DST}"
    # Register the harness in simple_fuzzers if not already present.
    if ! grep -q "sd-hwdb/fuzz-hwdb.c" "${MESON_FILE}"; then
        # Append to the existing `simple_fuzzers += files(` block.
        python3 - "${MESON_FILE}" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
m = re.search(r"simple_fuzzers \+= files\(\n", s)
assert m, "no simple_fuzzers block in " + p
i = m.end()
s = s[:i] + "        'sd-hwdb/fuzz-hwdb.c',\n" + s[i:]
open(p, "w").write(s)
PY
    fi
}

configure() {
    # $1 = build dir, $2 = sanitize arg ("" for cov)
    local BUILD="$1" SAN="$2"
    rm -rf "${BUILD}"
    local SAN_ARGS=()
    if [ -n "${SAN}" ]; then
        SAN_ARGS+=("-Db_sanitize=${SAN}")
    fi
    env CC=clang CXX=clang++ \
        meson setup "${BUILD}" "${SRC}" \
            -Dllvm-fuzz=true \
            -Db_lundef=false \
            -Dmode=developer \
            "${SAN_ARGS[@]}" \
            -Dfuzz-tests=true
}

if [ "${cmd}" = "build-libs" ]; then
    install_harness
    # ASAN build dir (also carries the harness target); cov build dir.
    configure /src/build-asan address
    configure /src/build-cov  ""
    echo "systemd meson configured (asan + cov)"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan) BUILD=/src/build-asan ;;
        coverage)                       BUILD=/src/build-cov ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    meson compile -C "${BUILD}" fuzz-hwdb
    cp "${BUILD}/fuzz-hwdb" "${OUT}/harness"
    SO=$(find "${BUILD}" -name 'libsystemd-shared-*.so' | head -1)
    [ -n "$SO" ] && cp "$SO" "${OUT}/" && patchelf --set-rpath '$ORIGIN' "${OUT}/harness"
    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2; exit 2
