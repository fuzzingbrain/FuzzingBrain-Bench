#!/bin/bash
# Build script for krb5-01 harness.
# Produces one harness binary per config under /out/<config>/harness.

set -euo pipefail

CONFIG="${1:?usage: build.sh <config>}"
SRC=/src
OUT=/out/${CONFIG}

mkdir -p "${OUT}"

case "${CONFIG}" in
    debug)        CFLAGS="-g -O0"; SAN="-fsanitize=fuzzer" ;;
    debug-asan)   CFLAGS="-g -O0"; SAN="-fsanitize=fuzzer,address" ;;
    release-asan) CFLAGS="-O2 -g"; SAN="-fsanitize=fuzzer,address" ;;
    coverage)     CFLAGS="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; SAN="-fsanitize=fuzzer" ;;
    *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
esac

cd "${SRC}/krb5/src"
if [ ! -f "Makefile" ]; then
    autoreconf -fi
    ./configure --enable-maintainer-mode
fi
make -j$(nproc)

clang \
    ${CFLAGS} \
    ${SAN} \
    -fmacro-prefix-map="${SRC}/=" \
    -I "${SRC}/krb5/src/include" \
    -I "${SRC}/krb5/src/lib/gssapi/mechglue" \
    -I "${SRC}/krb5/src/lib/gssapi/krb5" \
    "${SRC}/harness/harness.c" \
    "${SRC}/krb5/src/lib/gssapi/.libs/libgssapi_krb5.a" \
    "${SRC}/krb5/src/lib/krb5/.libs/libkrb5.a" \
    "${SRC}/krb5/src/lib/k5crypto/.libs/libk5crypto.a" \
    "${SRC}/krb5/src/lib/com_err/.libs/libcom_err.a" \
    "${SRC}/krb5/src/util/support/.libs/libkrb5support.a" \
    -lpthread \
    -ldl \
    -o "${OUT}/harness"

echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
