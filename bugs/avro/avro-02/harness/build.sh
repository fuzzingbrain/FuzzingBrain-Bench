#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

AVRO_DIR=/src/avro/lang/c

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) CF="-fsanitize=address -g -O1"; LF="-fsanitize=address" ;;
            cov)  CF="-fprofile-instr-generate -fcoverage-mapping -g -O0"; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        cp -r /src/avro /src/avro-${CONFIG_LIB}
        BUILD_DIR=/src/avro-${CONFIG_LIB}/lang/c/build
        mkdir -p "${BUILD_DIR}"
        pushd "${BUILD_DIR}" >/dev/null
        env CC=clang CXX=clang++ CFLAGS="${CF}" CXXFLAGS="${CF}" LDFLAGS="${LF}" \
            cmake .. \
                -DCMAKE_BUILD_TYPE=Debug \
                -DBUILD_SHARED_LIBS=OFF \
                -DTHREADSAFE=true \
                -DAVRO_ADD_PROTECTOR_FLAGS=0
        make -j${JOBS} avro-static
        popd >/dev/null
    done
    echo "avro C libs built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; BUILD=/src/avro-asan; SAN="-fsanitize=fuzzer,address" ;;
        debug-asan)   CFH="-g -O0"; BUILD=/src/avro-asan; SAN="-fsanitize=fuzzer,address" ;;
        release-asan) CFH="-O2 -g"; BUILD=/src/avro-asan; SAN="-fsanitize=fuzzer,address" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; BUILD=/src/avro-cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    clang ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -I "${BUILD}/lang/c/src" \
        -I "${BUILD}/lang/c/build/src" \
        /src/harness/datafile_fuzzer.c \
        "${BUILD}/lang/c/build/src/libavro.a" \
        -ljansson -lz -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
