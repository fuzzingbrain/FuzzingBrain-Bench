#!/bin/bash
# Build script for flatbuffers-parser-deserialize-uaf.
# Builds libflatbuffers (the full IDL/reflection library) static, twice
# (asan, coverage), then links the libFuzzer harness against it.
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)

FB_DIR=/src/flatbuffers

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS
    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ;;
        esac
        cmake -S "${FB_DIR}" -B /src/build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_CXX_FLAGS="${INSTR}" \
            -DCMAKE_EXE_LINKER_FLAGS="${INSTR}" \
            -DBUILD_SHARED_LIBS=OFF \
            -DFLATBUFFERS_BUILD_TESTS=OFF \
            -DFLATBUFFERS_BUILD_FLATC=OFF \
            -DFLATBUFFERS_BUILD_FLATHASH=OFF \
            -DFLATBUFFERS_INSTALL=OFF \
            >/dev/null
        cmake --build /src/build-${CONFIG_LIB} -j${JOBS} --target flatbuffers >/dev/null 2>&1
    done
    echo "libflatbuffers built"
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
        -std=c++17 \
        -fmacro-prefix-map=/src/= \
        -I "${FB_DIR}/include" \
        "/src/harness/flatbuffers_deserialize_fuzzer.cc" \
        "${BUILD}/libflatbuffers.a" \
        -lpthread \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
