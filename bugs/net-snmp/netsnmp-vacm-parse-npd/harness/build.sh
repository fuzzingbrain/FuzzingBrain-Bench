#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh build-libs | harness <config>}"

if [ "${cmd}" = "build-libs" ]; then
    JOBS=$(nproc)
    unset MAKEFLAGS MFLAGS

    for CONFIG_LIB in asan cov; do
        case "${CONFIG_LIB}" in
            asan) CF="-fsanitize=address,undefined -fno-sanitize-recover=undefined -g -O1"; LF="-fsanitize=address,undefined" ;;
            cov)  CF="-fprofile-instr-generate -fcoverage-mapping -g -O0"; LF="-fprofile-instr-generate -fcoverage-mapping" ;;
        esac

        cp -r /src/net-snmp /src/build-${CONFIG_LIB}
        pushd /src/build-${CONFIG_LIB} >/dev/null
        env CC=clang CFLAGS="${CF}" LDFLAGS="${LF}" \
            ./configure --disable-shared --enable-static \
                        --disable-agent --disable-applications \
                        --disable-manuals --disable-scripts \
                        --without-openssl --with-defaults
        make -j${JOBS} -C snmplib
        popd >/dev/null
    done
    echo "net-snmp libs built"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        debug)        CFH="-g -O0"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address,undefined -fno-sanitize-recover=undefined" ;;
        debug-asan)   CFH="-g -O0"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address,undefined -fno-sanitize-recover=undefined" ;;
        release-asan) CFH="-O2 -g"; BUILD=/src/build-asan; SAN="-fsanitize=fuzzer,address,undefined -fno-sanitize-recover=undefined" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; BUILD=/src/build-cov; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    clang ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -I "${BUILD}/include" \
        /src/harness/vacm_fuzzer.c \
        "${BUILD}/snmplib/.libs/libnetsnmp.a" \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
