#!/bin/bash
# Build script for flatbuffers-03.
# Builds libflatbuffers static (asan, coverage), generates the
# monster_test.bfbs schema the harness loads at startup, then links the
# libFuzzer harness. The harness loads "monster_test.bfbs" from the
# directory of the executable (LLVMFuzzerInitialize), so the schema is
# copied next to each built harness.
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
            -DFLATBUFFERS_BUILD_FLATC=ON \
            -DFLATBUFFERS_BUILD_FLATHASH=OFF \
            -DFLATBUFFERS_INSTALL=OFF \
            >/dev/null
        cmake --build /src/build-${CONFIG_LIB} -j${JOBS} --target flatbuffers flatc >/dev/null 2>&1
    done

    # Generate monster_test.bfbs (the schema the harness loads at runtime).
    FLATC_BIN="$(find /src/build-asan -maxdepth 2 -name flatc -type f | head -1)"
    mkdir -p /src/schema
    "${FLATC_BIN}" --binary --schema -o /src/schema \
        -I "${FB_DIR}/tests/include_test" \
        "${FB_DIR}/tests/monster_test.fbs"
    ls -la /src/schema/monster_test.bfbs
    echo "libflatbuffers + libflatc built; monster_test.bfbs generated"
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

    FB_LIB="$(find "${BUILD}" -name 'libflatbuffers.a' | head -1)"

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -std=c++17 \
        -fmacro-prefix-map=/src/= \
        -I "${FB_DIR}/include" \
        "/src/harness/flatbuffers_reflection_gentext_fuzzer.cc" \
        "${FB_LIB}" \
        -lpthread \
        -o "${OUT}/harness"

    # The harness loads monster_test.bfbs from the executable's directory.
    cp /src/schema/monster_test.bfbs "${OUT}/monster_test.bfbs"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
