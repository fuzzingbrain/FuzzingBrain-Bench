#!/bin/bash
set -euxo pipefail

export MODE=${1:-debug}

cd /src/krb5

if [ ! -f ./configure ]; then
    echo "[!] No configure found. Expecting pre-generated build system."
    exit 1
fi

CFLAGS="-O0 -g -fno-omit-frame-pointer -fPIC"
ASAN_FLAGS="-fsanitize=address,fuzzer-no-link"

case "$MODE" in
  debug)
    ./configure --disable-shared --enable-static CFLAGS="$CFLAGS"
    make -j$(nproc)
    ;;

  debug-asan)
    ./configure --disable-shared --enable-static CC=clang CFLAGS="$CFLAGS $ASAN_FLAGS"
    make -j$(nproc)
    ;;

  release-asan)
    ./configure --disable-shared --enable-static CC=clang CFLAGS="-O2 $ASAN_FLAGS"
    make -j$(nproc)
    ;;

  coverage)
    ./configure --disable-shared --enable-static CC=clang CFLAGS="$CFLAGS --coverage"
    make -j$(nproc)
    ;;

esac

$CXX $CXXFLAGS \
  -I/src/krb5/src/include \
  /src/krb5/src/tests/fuzzing/fuzz_gss.c \
  -o /out/fuzz_gss \
  -L/src/krb5/src/lib/gssapi/krb5/.libs \
  -L/src/krb5/src/lib/krb5/.libs \
  -lFuzzingEngine \
  -lgssapi_krb5 -lkrb5 -lk5crypto -lcom_err -lkrb5support
