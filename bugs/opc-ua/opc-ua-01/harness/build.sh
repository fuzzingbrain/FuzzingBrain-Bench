#!/bin/bash
# Build script for opc-ua-01.
# Builds open62541 (PubSub + JSON) static, twice (asan, coverage), then links
# the libFuzzer harness together with the in-tree custom_memory_manager.c.
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)
FUZZDIR=/src/open62541/tests/fuzz

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS
    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ;;
        esac
        cmake -S /src/open62541 -B /src/build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_CXX_FLAGS="${INSTR}" \
            -DCMAKE_INSTALL_PREFIX=/src/install-${CONFIG_LIB} \
            -DBUILD_SHARED_LIBS=OFF \
            -DUA_ENABLE_PUBSUB=ON \
            -DUA_ENABLE_JSON_ENCODING=ON \
            -DUA_ENABLE_MALLOC_SINGLETON=ON \
            -DUA_ENABLE_AMALGAMATION=OFF \
            -DUA_BUILD_FUZZING=OFF \
            -DUA_BUILD_EXAMPLES=OFF >/dev/null
        cmake --build /src/build-${CONFIG_LIB} -j${JOBS} --target open62541 >/dev/null 2>&1
        cmake --install /src/build-${CONFIG_LIB} >/dev/null 2>&1
    done
    echo "open62541 built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_H="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            PREFIX=/src/install-asan
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            PREFIX=/src/install-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    LIB=$(find "${PREFIX}" -name 'libopen62541.a' | head -1)

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -fmacro-prefix-map=/src/= \
        -I "${PREFIX}/include" -I "${FUZZDIR}" \
        -x c "${FUZZDIR}/custom_memory_manager.c" \
        -x c++ "/src/harness/fuzz_pubsub_json.cc" \
        -x none "${LIB}" \
        -lm -lpthread \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
