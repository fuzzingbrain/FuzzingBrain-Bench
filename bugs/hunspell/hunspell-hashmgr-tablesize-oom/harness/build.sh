#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

# hunspell is autotools. The library is built once per sanitizer flavor with an
# out-of-tree (VPATH) build so the pristine /src/hunspell tree stays clean. The
# static archive lands at <builddir>/src/hunspell/.libs/libhunspell-1.7.a.
#
# CRITICAL: we do NOT define FUZZING_BUILD_MODE_UNSAFE_FOR_PRODUCTION. That macro
# caps HashMgr::load_tables' max_allowed to ~1248 entries and gates out the bug.
# Production builds (and this benchmark) get the full INT_MAX/sizeof(hentry*)
# ceiling, which is what makes the 200,000,000-entry .dic header reach the
# unbounded resize().

SRC=/src/hunspell

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    # Generate the configure script once in the source tree.
    if [ ! -x "${SRC}/configure" ]; then
        ( cd "${SRC}" && autoreconf -vfi )
    fi

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) CF="-fsanitize=address -g -O1 -fno-omit-frame-pointer"; LF="-fsanitize=address" ;;
            cov)  CF="-fprofile-instr-generate -fcoverage-mapping -g -O0"; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        BUILD_DIR=/src/build-${CONFIG_LIB}
        mkdir -p "${BUILD_DIR}"
        pushd "${BUILD_DIR}" >/dev/null
        env CC=clang CXX=clang++ CFLAGS="${CF}" CXXFLAGS="${CF}" LDFLAGS="${LF}" \
            "${SRC}/configure" \
                --disable-shared \
                --enable-static \
                --without-readline
        make -j"${JOBS}"
        popd >/dev/null
    done
    echo "hunspell libs built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address" ;;
        debug-asan)   CFH="-g -O0"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address" ;;
        release-asan) CFH="-O1 -g -fno-omit-frame-pointer"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; BUILD=/src/build-cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    clang++ -std=c++17 ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -I "${SRC}/src" \
        /src/harness/hunspell_hashmgr_dic_loader_fuzzer.cc \
        "${BUILD}/src/hunspell/.libs/libhunspell-1.7.a" \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
