#!/bin/bash
# Build for systemd-pe-binary-dos.
#
# systemd uses the Meson build system. The libFuzzer harness fuzz-pe-binary.c
# uses systemd-internal headers (pe-binary.h, uki.h, fuzz.h, tests.h,
# memfd-util.h, crypto-util.h, ...) and must be linked against
# libsystemd-shared, so it is built *through* Meson via the existing
# `simple_fuzzers` machinery rather than hand-rolled with clang.
#
# At the vuln_commit the upstream fuzzer src/fuzz/fuzz-pe-binary.c does not
# exist yet (it was added by the fix PR #42348). We drop our harness copy in
# at that canonical path and append it to the simple_fuzzers list in
# src/fuzz/meson.build. Meson with -Dllvm-fuzz=true then emits a libFuzzer
# binary named `fuzz-pe-binary`.
#
# This is a slow-unit / algorithmic-complexity DoS, so the resulting binary
# must be run under libFuzzer's wall-clock alarm (see bench.yaml invocation
# `-timeout=10`); the unit does not return on its own.
#
# NOTE (build feasibility): compiles a large fraction of systemd
# (libsystemd-shared). Heavy but bounded; see NOTES.md. OpenSSL is required
# so the HAVE_OPENSSL path in the harness (uki_hash) is compiled in — that
# is the path containing the expensive zero-padding hash loop.
set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"
SRC=/src/systemd
HARNESS_DST="${SRC}/src/fuzz/fuzz-pe-binary.c"
MESON_FILE="${SRC}/src/fuzz/meson.build"

install_harness() {
    cp /src/harness/fuzz-pe-binary.c "${HARNESS_DST}"
    if ! grep -q "'fuzz-pe-binary.c'" "${MESON_FILE}"; then
        python3 - "${MESON_FILE}" <<'PY'
import sys, re
p = sys.argv[1]
s = open(p).read()
m = re.search(r"simple_fuzzers \+= files\(\n", s)
assert m, "no simple_fuzzers block in " + p
i = m.end()
s = s[:i] + "        'fuzz-pe-binary.c',\n" + s[i:]
open(p, "w").write(s)
PY
    fi
}

configure() {
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

    meson compile -C "${BUILD}" fuzz-pe-binary
    cp "${BUILD}/fuzz-pe-binary" "${OUT}/harness"
    SO=$(find "${BUILD}" -name 'libsystemd-shared-*.so' | head -1)
    [ -n "$SO" ] && cp "$SO" "${OUT}/" && patchelf --set-rpath '$ORIGIN' "${OUT}/harness"
    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2; exit 2
