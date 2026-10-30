#!/bin/bash
# Build script for libaom-02.
# Builds libaom (encoder + RateControlRTC interface) static, twice
# (asan, coverage), then links the libFuzzer harness against av1/ratectrl_rtc.h.
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
        cmake -S /src/aom -B /src/build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_CXX_FLAGS="${INSTR}" \
            -DCMAKE_EXE_LINKER_FLAGS="${INSTR}" \
            -DBUILD_SHARED_LIBS=OFF \
            -DCONFIG_AV1_ENCODER=1 -DCONFIG_AV1_DECODER=0 \
            -DCONFIG_REALTIME_ONLY=1 \
            -DENABLE_TESTS=0 -DENABLE_EXAMPLES=0 -DENABLE_TOOLS=0 -DENABLE_DOCS=0 \
            >/dev/null
        cmake --build /src/build-${CONFIG_LIB} -j${JOBS} --target aom aom_av1_rc >/dev/null 2>&1
    done
    echo "libaom built"
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
        -fmacro-prefix-map=/src/= \
        -I "/src/aom" -I "${BUILD}" \
        "/src/harness/av1_config_fuzzer.cc" \
        -x c "/src/aom/common/av1_config.c" -x none \
        "${BUILD}/libaom.a" \
        -lm -lpthread \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
