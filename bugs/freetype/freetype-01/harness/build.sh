#!/bin/bash
# Build script for freetype-01.
# FreeType builds cleanly with CMake. We build it as a static, instrumented
# library with the bundled rasterizers (smooth renderer is the one that
# allocates the bitmap buffer that gets used-after-free), then link the
# extracted libFuzzer harness against it. No external deps required: zlib,
# bzip2, png, harfbuzz, brotli are all disabled so the binary is
# self-contained.

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ;;
        esac
        cmake -S /src/freetype -B /src/ft-build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DBUILD_SHARED_LIBS=OFF \
            -DFT_DISABLE_ZLIB=ON \
            -DFT_DISABLE_BZIP2=ON \
            -DFT_DISABLE_PNG=ON \
            -DFT_DISABLE_HARFBUZZ=ON \
            -DFT_DISABLE_BROTLI=ON >/dev/null
        cmake --build /src/ft-build-${CONFIG_LIB} -j${JOBS} --target freetype >/dev/null 2>&1
    done
    echo "freetype built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_H="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            BUILD=/src/ft-build-asan
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            BUILD=/src/ft-build-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    LIBFT_A=$(find "${BUILD}" -name 'libfreetype*.a' -type f | head -1)
    [ -n "${LIBFT_A}" ] || { echo "ERROR: libfreetype.a not found under ${BUILD}"; find /src -name 'libfreetype*' ; exit 3; }

    clang \
        ${CFLAGS_H} \
        ${SAN} \
        -fmacro-prefix-map=/src/= \
        -I "/src/freetype/include" \
        "/src/harness/ftfuzzer_glyph.c" \
        -Wl,--start-group "${LIBFT_A}" -Wl,--end-group \
        -lm -lpthread -ldl \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
