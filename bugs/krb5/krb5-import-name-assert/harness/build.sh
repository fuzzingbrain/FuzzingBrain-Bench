#!/bin/bash
set -euo pipefail

CONFIG="${1:?usage: build.sh <config>}"
OUT="/out/${CONFIG}"
mkdir -p "${OUT}"

case "${CONFIG}" in
    debug)
        CFLAGS="-g -O0"
        SAN="-fsanitize=fuzzer"
        ;;
    debug-asan)
        CFLAGS="-g -O0"
        SAN="-fsanitize=fuzzer,address"
        ;;
    release-asan)
        CFLAGS="-O2 -g"
        SAN="-fsanitize=fuzzer,address"
        ;;
    coverage)
        CFLAGS="-g -O0 -fprofile-instr-generate -fcoverage-mapping"
        SAN="-fsanitize=fuzzer"
        ;;
    *)
        echo "unknown config: ${CONFIG}" >&2
        exit 2
        ;;
esac

echo "[*] checking fuzz file"
ls -la /src/krb5/src/tests/fuzzing/

find /src/krb5 -name "*fuzz*" || true

echo "[*] Building krb5 (base system)..."

pushd /src/krb5/src >/dev/null

autoreconf -fi

./configure \
    CC=clang \
    CFLAGS="-fcommon ${CFLAGS}" \
    --enable-static \
    --disable-shared

make -j"$(nproc)"

popd >/dev/null

echo "[*] Building fuzz harness directly (libFuzzer entrypoint)..."

clang++ \
  ${SAN} \
  ${CFLAGS} \
  /src/krb5/src/tests/fuzzing/fuzz_gss.c \
  /src/krb5/src/lib/krb5/.libs/libkrb5.a \
  /src/krb5/src/lib/gssapi/krb5/.libs/libgssapi_krb5.a \
  /src/krb5/src/lib/krb5support/libkrb5support.a \
  -o "${OUT}/harness"

echo "[+] built ${OUT}/harness"
ls -lh "${OUT}/harness"
