#!/bin/sh
# cups ./configure runs link+RUN tests; an ASan-instrumented conftest fails to
# execute under buildkit's restricted personality ("cannot create executables").
# So configure with the bare driver and inject ASan only at make time via OPTIM
# (compile flags). libcups.a is a static archive, so the ASan runtime is supplied
# later when the harness links with -fsanitize=fuzzer,address.
set -eu
cmd="${1:?usage: build.sh build-libs | harness <config>}"
SRC=/src/cups
ASAN="-fsanitize=address -g -O1 -fno-omit-frame-pointer"

if [ "${cmd}" = "build-libs" ]; then
    cd "${SRC}"
    ./configure --disable-shared CC=clang CXX=clang++
    make -C cups libcups.a OPTIM="${ASAN}"
    cp "${SRC}/cups/libcups.a" /src/libcups-asan.a
    echo "cups lib built: $(ls -la /src/libcups-asan.a)"
    exit 0
fi

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"; OUT="/out/${CONFIG}"; mkdir -p "${OUT}"
    clang++ -fsanitize=fuzzer,address -g -O1 -fno-omit-frame-pointer \
        -I"${SRC}" -I"${SRC}/cups" \
        /src/harness/fuzz_transcode.cc /src/libcups-asan.a \
        -lz -lpthread -lm -lssl -lcrypto -lavahi-client -lavahi-common -o "${OUT}/harness"
    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
echo "unknown subcommand ${cmd}" >&2; exit 2
