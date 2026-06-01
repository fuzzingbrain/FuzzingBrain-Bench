#!/bin/bash
# Build script for libheif-image-crop-overflow.
# libheif needs an HEVC decoder. We build libde265 from source as a static
# lib (uninstrumented — ASan still tracks its heap via malloc interposition,
# and the overflowed buffer is allocated in libheif itself), then build
# libheif static against it with the decoder linked in (no dlopen plugins),
# so the extracted harness binary is self-contained.

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)
DE265_PREFIX=/src/de265-install

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS

    # --- libde265 (static, no sanitizer) ---
    cmake -S /src/libde265 -B /src/de265-build \
        -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=${DE265_PREFIX} \
        -DBUILD_SHARED_LIBS=OFF \
        -DENABLE_SDL=OFF -DENABLE_DECODER=OFF -DENABLE_ENCODER=OFF >/dev/null
    cmake --build /src/de265-build -j${JOBS} >/dev/null 2>&1
    cmake --install /src/de265-build >/dev/null 2>&1

    # --- libheif (static, instrumented) ---
    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ;;
        esac
        cmake -S /src/libheif -B /src/heif-build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_CXX_FLAGS="${INSTR}" \
            -DCMAKE_PREFIX_PATH=${DE265_PREFIX} \
            -DBUILD_SHARED_LIBS=OFF \
            -DENABLE_PLUGIN_LOADING=OFF \
            -DWITH_LIBDE265=ON \
            -DWITH_AOM_DECODER=OFF -DWITH_AOM_ENCODER=OFF \
            -DWITH_X265=OFF -DWITH_DAV1D=OFF -DWITH_SvtEnc=OFF -DWITH_RAV1E=OFF \
            -DWITH_JPEG_DECODER=OFF -DWITH_JPEG_ENCODER=OFF \
            -DWITH_OpenJPEG_DECODER=OFF -DWITH_OpenJPEG_ENCODER=OFF \
            -DWITH_UNCOMPRESSED_CODEC=OFF \
            -DWITH_EXAMPLES=OFF -DBUILD_TESTING=OFF >/dev/null
        cmake --build /src/heif-build-${CONFIG_LIB} -j${JOBS} --target heif >/dev/null 2>&1
    done
    echo "libheif + libde265 built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_H="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            BUILD=/src/heif-build-asan
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            BUILD=/src/heif-build-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    LIBHEIF_A=$(find "${BUILD}" -name 'libheif.a' -type f | head -1)
    LIBDE265_A=$(find "${DE265_PREFIX}" -name 'libde265.a' -type f | head -1)

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -std=c++17 \
        -fmacro-prefix-map=/src/= \
        -I "/src/libheif" -I "/src/libheif/libheif/api" -I "${BUILD}" \
        "/src/harness/image_transform_fuzzer.cc" \
        "${LIBHEIF_A}" \
        "${LIBDE265_A}" \
        -lstdc++ -lm -lpthread -ldl \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
