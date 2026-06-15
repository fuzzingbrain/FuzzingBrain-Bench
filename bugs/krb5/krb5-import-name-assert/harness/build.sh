#!/bin/bash
# Build script for krb5-import-name-assert harness.
# Based on src/tests/fuzzing/oss-fuzz.sh from the krb5 source tree.
# Produces one harness binary per config under /out/<config>/harness.
set -euo pipefail
CONFIG="${1:?usage: build.sh <config>}"
OUT=/out/${CONFIG}
mkdir -p "${OUT}"
case "${CONFIG}" in
    debug)        CFLAGS="-g -O0"; SAN="-fsanitize=fuzzer" ;;
    debug-asan)   CFLAGS="-g -O0"; SAN="-fsanitize=fuzzer,address" ;;
    release-asan) CFLAGS="-O2 -g"; SAN="-fsanitize=fuzzer,address" ;;
    coverage)     CFLAGS="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; SAN="-fsanitize=fuzzer" ;;
    *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
esac
# Build krb5 at the vulnerable commit.
# OSS-Fuzz image provides clang and build dependencies (autoconf, bison).
pushd /src/krb5/src/
autoreconf
./configure CC=clang CFLAGS="-fcommon ${CFLAGS}" \
    --enable-static --disable-shared --enable-ossfuzz
make -j$(nproc)
popd
# Copy the fuzz_gss harness binary to out.
cp /src/krb5/src/tests/fuzzing/fuzz_gss "${OUT}/harness"
echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
