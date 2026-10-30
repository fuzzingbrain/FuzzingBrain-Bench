#!/bin/bash
# Build script for libvpx-03.
# UBSan-detected NaN->int cast: ASan alone does not flag it, so the asan
# library build and the asan harness configs add -fsanitize=undefined.
# libvpx uses its own configure (out-of-tree). Build static twice (asan+ubsan,
# coverage), then link the libFuzzer harness against libvpx.a.
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS
    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1 -fno-omit-frame-pointer" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ;;
        esac
        mkdir -p /src/build-${CONFIG_LIB}
        # libvpx's configure runs link tests with the bare driver and does not
        # propagate --extra-cflags into them; bake the sanitizer flags into
        # CC/CXX so those link tests see them too.
        ( cd /src/build-${CONFIG_LIB} && \
          CC="clang ${INSTR}" CXX="clang++ ${INSTR}" \
          LDFLAGS="${INSTR}" \
          /src/libvpx/configure \
            --target=x86_64-linux-gcc \
            --disable-shared --enable-static --enable-debug --disable-optimizations \
            --disable-examples --disable-tools --disable-docs --disable-unit-tests \
            --enable-vp8 --enable-vp9 \
            --enable-vp9-encoder --enable-vp9-decoder \
            --enable-error-concealment \
            --extra-cflags="-g -O1" --extra-cxxflags="-g -O1" --enable-pic >/dev/null && \
          make -j${JOBS} >/dev/null 2>&1 )
    done
    echo "libvpx built"
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
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            BUILD=/src/build-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -fno-omit-frame-pointer \
        -fmacro-prefix-map=/src/= \
        -fdebug-prefix-map=/src/= \
        -I "/src/libvpx" -I "${BUILD}" \
        "/src/harness/vp9_encoder_config_fuzzer.cc" \
        "${BUILD}/libvpx.a" \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
