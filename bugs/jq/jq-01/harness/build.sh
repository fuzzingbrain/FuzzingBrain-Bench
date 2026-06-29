#!/bin/bash
# Build script for jq-01.
# jq uses autoconf and bundles oniguruma as a submodule. Builds done
# in-tree (copy source twice — once for asan, once for coverage).

set -euo pipefail

cmd="${1:?usage: build.sh build-libs | harness <config>}"

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)

    # Initialize submodules once in the canonical /src/jq
    git -C /src/jq submodule update --init --recursive
    (cd /src/jq && autoreconf -fi >/dev/null 2>&1)

    # asan build
    cp -r /src/jq /src/jq-asan
    pushd /src/jq-asan >/dev/null
    CC=clang CXX=clang++ \
        CFLAGS="-fsanitize=address -g -O1" \
        CXXFLAGS="-fsanitize=address -g -O1" \
        LDFLAGS="-fsanitize=address" \
        ./configure --with-oniguruma=builtin --enable-static --disable-shared >/dev/null
    make -j${JOBS} >/dev/null 2>&1
    popd >/dev/null

    # coverage build
    cp -r /src/jq /src/jq-cov
    pushd /src/jq-cov >/dev/null
    CC=clang CXX=clang++ \
        CFLAGS="-fprofile-instr-generate -fcoverage-mapping -g -O0" \
        CXXFLAGS="-fprofile-instr-generate -fcoverage-mapping -g -O0" \
        LDFLAGS="-fprofile-instr-generate -fcoverage-mapping" \
        ./configure --with-oniguruma=builtin --enable-static --disable-shared >/dev/null
    make -j${JOBS} >/dev/null 2>&1
    popd >/dev/null

    echo "jq libs built (asan + coverage)"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"

    case "${CONFIG}" in
        debug|debug-asan|release-asan)
            CFLAGS_HARNESS="$([ "${CONFIG}" = "release-asan" ] && echo "-O2 -g" || echo "-g -O0")"
            BUILD=/src/jq-asan
            SAN="-fsanitize=fuzzer,address"
            ;;
        coverage)
            CFLAGS_HARNESS="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
            BUILD=/src/jq-cov
            SAN="-fsanitize=fuzzer"
            ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    # vendor/oniguruma/src/.libs/libonig.a inside the source tree
    clang \
        ${CFLAGS_HARNESS} \
        ${SAN} \
        -fmacro-prefix-map=/src/= \
        -I "${BUILD}/src" -I "${BUILD}" \
        "/src/harness/jq_fuzz_compile.c" \
        "${BUILD}/.libs/libjq.a" \
        "${BUILD}/vendor/oniguruma/src/.libs/libonig.a" \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi

echo "unknown subcommand: ${cmd}" >&2
exit 2
