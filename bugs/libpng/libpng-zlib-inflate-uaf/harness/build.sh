#!/bin/bash
# Build script for libpng-zlib-inflate-uaf.
# libpng builds with cmake and depends on system zlib. We build the static
# library twice (asan+ubsan, coverage) then link the libFuzzer harness.

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan)
                INSTR="-fsanitize=address,undefined -fno-sanitize-recover=undefined -g -O1"
                ;;
            cov)
                INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0"
                ;;
        esac

        cmake -S /src/libpng -B /src/build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang \
            -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Release \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_CXX_FLAGS="${INSTR}" \
            -DCMAKE_EXE_LINKER_FLAGS="${INSTR}" \
            -DPNG_SHARED=OFF \
            -DPNG_STATIC=ON \
            -DPNG_TESTS=OFF \
            -DPNG_TOOLS=OFF >/dev/null
        cmake --build /src/build-${CONFIG_LIB} -j${JOBS} --target png_static >/dev/null 2>&1
    done
    echo "libpng libs built (asan + coverage)"
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

    LIBPNG_A=$(find "${BUILD}" -name 'libpng*.a' -type f | head -1)

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -fmacro-prefix-map=/src/= \
        -I "/src/libpng" -I "${BUILD}" \
        "/src/harness/libpng_unknown_chunk_dispatch_fuzzer.cc" \
        "${LIBPNG_A}" \
        -lz \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
