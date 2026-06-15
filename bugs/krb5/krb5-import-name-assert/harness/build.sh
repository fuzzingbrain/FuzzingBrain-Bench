#!/bin/bash
set -euxo pipefail

MODE=${1:-debug}

cd /src/krb5

autoreconf -fi

./configure \
  --disable-shared \
  --enable-static \
  CFLAGS="-O0 -g -fno-omit-frame-pointer" \
  LDFLAGS="-L/src/krb5/src/lib/krb5/.libs \
           -L/src/krb5/src/lib/gssapi/krb5/.libs \
           -L/src/krb5/src/lib/krb5support \
           -L/src/krb5/src/lib/krb5"

make -j$(nproc)

make install DESTDIR=/out/krb5

cd /src/harness

clang++ -g -O0 \
  -I/src/krb5/src/include \
  fuzz_*.c fuzz_*.cc 2>/dev/null || true

clang++ -g -O0 \
  fuzz_*.o \
  -L/out/krb5/usr/local/lib \
  -lkrb5 -lgssapi_krb5 -lkrb5support -lcom_err \
  -o /out/debug/harness
