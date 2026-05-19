#!/bin/bash
# Build script for ots-processgeneric-npd.
# Uses meson; depends on system freetype/brotli/zlib (sanitizer-uninstrumented,
# which is fine — the bug is in ots itself, not in those deps).

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan)
                INSTR_C="-fsanitize=address,undefined -fno-sanitize-recover=undefined -g -O1"
                INSTR_L="-fsanitize=address,undefined"
                ;;
            cov)
                INSTR_C="-fprofile-instr-generate -fcoverage-mapping -g -O0"
                INSTR_L="-fprofile-instr-generate -fcoverage-mapping"
                ;;
        esac

        CC=clang CXX=clang++ \
        meson setup /src/build-${CONFIG_LIB} /src/ots \
            --buildtype=plain \
            --default-library=static \
            --wrap-mode=default \
            -Dc_args="${INSTR_C}" \
            -Dcpp_args="${INSTR_C}" \
            -Dc_link_args="${INSTR_L}" \
            -Dcpp_link_args="${INSTR_L}"
        # Build everything; explicit `ots` target name doesn't exist
        ninja -C /src/build-${CONFIG_LIB} -j${JOBS}
    done

    echo "ots libs built (asan + cov)"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_H="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            BUILD=/src/build-asan
            SAN="-fsanitize=fuzzer,address,undefined -fno-sanitize-recover=undefined"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            BUILD=/src/build-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    # Discover all archives meson built (libots + subproject libs)
    LIBS=$(find "${BUILD}" -name '*.a' -type f)

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -fmacro-prefix-map=/src/= \
        -I /src/ots/include \
        /src/harness/passthru_harness.cc \
        ${LIBS} \
        -lz -lbrotlidec -lbrotlienc -lbrotlicommon -llz4 -lwoff2dec \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
