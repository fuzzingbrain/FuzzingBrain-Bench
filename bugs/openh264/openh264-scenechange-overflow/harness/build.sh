#!/bin/bash
# Build script for openh264-scenechange-overflow.
# OpenH264 builds with its own GNU make. The `make libraries` target produces a
# combined static archive libopenh264.a that contains the common + processing
# module objects (where WelsSampleSad8x8_c and the scene-change detector live).
# We build it instrumented and C-only (USE_ASM=No) so the C reference SAD path
# (WelsSampleSad8x8_c) is the one that runs and ASan can see the OOB read.
# OpenH264 builds in-tree, so we use a separate source copy per config.

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1 -fPIC" ; LF="-fsanitize=address" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0 -fPIC" ; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        cp -r /src/openh264 /src/oh-${CONFIG_LIB}
        make -C /src/oh-${CONFIG_LIB} -j${JOBS} \
            CC=clang CXX=clang++ \
            USE_ASM=No \
            CFLAGS_OPT="" \
            CFLAGS="${INSTR}" CXXFLAGS="${INSTR}" LDFLAGS="${LF}" \
            libraries >/dev/null 2>&1
    done
    echo "openh264 built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_H="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            SRC=/src/oh-asan
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            SRC=/src/oh-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    LIBOH_A=$(find "${SRC}" -maxdepth 1 -name 'libopenh264.a' -type f | head -1)

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -std=c++11 \
        -fmacro-prefix-map=/src/= \
        -I "${SRC}/codec/processing/interface" \
        -I "${SRC}/codec/common/inc" \
        "/src/harness/processing_fuzzer.cpp" \
        "${LIBOH_A}" \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
