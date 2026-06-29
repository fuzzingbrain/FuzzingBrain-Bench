#!/bin/bash
# Build script for libwebsockets-01.
# subsystem, reached via lws_lhp_parse. We build libwebsockets as a static,
# instrumented library with LHP + DLO enabled (both default ON) and SSL/network
# extras disabled so the harness binary is self-contained, then link the
# extracted libFuzzer harness against it.

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1" ; LF="-fsanitize=address" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac
        cmake -S /src/libwebsockets -B /src/lws-build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_EXE_LINKER_FLAGS="${LF}" \
            -DLWS_WITH_STATIC=ON -DLWS_WITH_SHARED=OFF \
            -DLWS_WITH_LHP=ON \
            -DLWS_WITH_DLO=ON \
            -DLWS_WITH_SECURE_STREAMS=ON \
            -DLWS_WITH_SSL=OFF \
            -DLWS_WITHOUT_TESTAPPS=ON \
            -DLWS_WITHOUT_TEST_SERVER=ON \
            -DLWS_WITHOUT_TEST_CLIENT=ON \
            -DLWS_WITH_MINIMAL_EXAMPLES=OFF >/dev/null
        cmake --build /src/lws-build-${CONFIG_LIB} -j${JOBS} --target websockets >/dev/null 2>&1
    done
    echo "libwebsockets built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_H="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            BUILD=/src/lws-build-asan
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_H="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            BUILD=/src/lws-build-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    LIBLWS_A=$(find "${BUILD}" -name 'libwebsockets.a' -type f | head -1)

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -std=c++11 \
        -fmacro-prefix-map=/src/= \
        -I "/src/libwebsockets/include" \
        -I "${BUILD}" \
        "/src/harness/lws_lhp_fuzzer.cc" \
        "${LIBLWS_A}" \
        -lpthread -lm -ldl -lcap \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
