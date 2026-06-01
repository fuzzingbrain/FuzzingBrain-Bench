#!/bin/bash
# Build script for spirv-orderblocks-segv.
# SPIRV-Tools builds with cmake and needs SPIRV-Headers (fetched via
# utils/git-sync-deps). We build the static lib twice (asan, coverage) and
# link the libFuzzer harness against the public C API.
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"
JOBS=$(nproc)

if [ "${cmd}" = "build-libs" ]; then
    unset MAKEFLAGS MFLAGS
    # Fetch external deps (SPIRV-Headers) once into the canonical tree.
    python3 /src/SPIRV-Tools/utils/git-sync-deps

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) INSTR="-fsanitize=address -g -O1" ;;
            cov)  INSTR="-fprofile-instr-generate -fcoverage-mapping -g -O0" ;;
        esac
        cmake -S /src/SPIRV-Tools -B /src/build-${CONFIG_LIB} \
            -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
            -DCMAKE_BUILD_TYPE=Debug \
            -DCMAKE_C_FLAGS="${INSTR}" \
            -DCMAKE_CXX_FLAGS="${INSTR}" \
            -DCMAKE_EXE_LINKER_FLAGS="${INSTR}" \
            -DBUILD_SHARED_LIBS=OFF \
            -DSPIRV_SKIP_TESTS=ON \
            -DSPIRV_SKIP_EXECUTABLES=ON >/dev/null
        cmake --build /src/build-${CONFIG_LIB} -j${JOBS} --target SPIRV-Tools-static >/dev/null 2>&1
    done
    echo "SPIRV-Tools built"
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

    # SPIRV-Tools static libs (core + common tables).
    LIBS=$(find "${BUILD}" -name 'libSPIRV-Tools*.a' -type f | tr '\n' ' ')

    clang++ \
        ${CFLAGS_H} \
        ${SAN} \
        -std=c++17 \
        -fmacro-prefix-map=/src/= \
        -I "/src/SPIRV-Tools/include" \
        "/src/harness/spirv_disasm_fuzzer.cc" \
        ${LIBS} \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
