#!/bin/bash
set -euo pipefail

CONFIG="${1:?usage: build.sh <config>}"
OUT="/out/${CONFIG}"
SRC="/src/krb5"

mkdir -p "${OUT}"

# Compiler flags per config (OSS-Fuzz style)
case "${CONFIG}" in
  debug)
    export CFLAGS="-O0 -g"
    export CXXFLAGS="-O0 -g"
    SAN="-fsanitize=fuzzer"
    ;;
  debug-asan)
    export CFLAGS="-O0 -g -fsanitize=address"
    export CXXFLAGS="-O0 -g -fsanitize=address"
    SAN="-fsanitize=fuzzer,address"
    ;;
  release-asan)
    export CFLAGS="-O2 -g -fsanitize=address"
    export CXXFLAGS="-O2 -g -fsanitize=address"
    SAN="-fsanitize=fuzzer,address"
    ;;
  coverage)
    export CFLAGS="-O0 -g -fprofile-instr-generate -fcoverage-mapping"
    export CXXFLAGS="-O0 -g -fprofile-instr-generate -fcoverage-mapping"
    SAN="-fsanitize=fuzzer"
    ;;
  *)
    echo "Unknown config: ${CONFIG}" >&2
    exit 1
    ;;
esac

cd "${SRC}/src"

# ---- Build krb5 normally (IMPORTANT: let autotools handle libs) ----
autoreconf -fi

./configure CC=clang CXX=clang++ \
    CFLAGS="-fcommon ${CFLAGS}" \
    --enable-static \
    --disable-shared \
    --enable-ossfuzz

make -j"$(nproc)"

# ---- Build fuzz harness (link against already built libs) ----
echo "[*] Building fuzz harness..."

clang++ \
    -std=c++17 \
    ${SAN} \
    -I"${SRC}/src/include" \
    "${SRC}/src/tests/fuzzing/fuzz_gss.c" \
    -o "${OUT}/harness" \
    "${LIB_FUZZING_ENGINE:-}" \
    lib/libkrb5support.a \
    lib/krb5/.libs/libkrb5.a \
    lib/gssapi/krb5/.libs/libgssapi_krb5.a

echo "[+] built ${OUT}/harness"
