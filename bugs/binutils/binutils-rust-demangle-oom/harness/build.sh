#!/bin/bash
set -euo pipefail
cmd="${1:?usage: build.sh harness <config>}"

# binutils-gdb's libiberty/rust-demangle.c is fully self-contained: it
# only pulls in safe-ctype.h/c, plus the public demangle.h. We compile
# the three TUs directly into the harness — no autotools dance needed.

REPO=/src/binutils-gdb

if [ "${cmd}" = "harness" ]; then
    CONFIG="${2:?harness needs <config>}"
    OUT=/out/${CONFIG}
    mkdir -p "${OUT}"
    case "${CONFIG}" in
        # Original fault is a libFuzzer out-of-memory (CWE-400), NOT an
        # ASan/UBSan error. Build with the fuzzer driver only; libFuzzer's
        # rss_limit_mb (default 2048) detects the OOM. No address/undefined.
        debug)        CFH="-g -O0"; SAN="-fsanitize=fuzzer" ;;
        debug-asan)   CFH="-g -O0"; SAN="-fsanitize=fuzzer,address" ;;
        release-asan) CFH="-O1 -g -fno-omit-frame-pointer"; SAN="-fsanitize=fuzzer,address" ;;
        coverage)     CFH="-g -O0 -fprofile-instr-generate -fcoverage-mapping"; SAN="-fsanitize=fuzzer" ;;
        *) echo "unknown config: ${CONFIG}" >&2; exit 2 ;;
    esac

    clang ${CFH} ${SAN} -fmacro-prefix-map=/src/= \
        -DHAVE_STRING_H -DHAVE_STDLIB_H \
        -I "${REPO}/include" \
        -I "${REPO}/libiberty" \
        /src/harness/fuzz_rust_demangle.c \
        "${REPO}/libiberty/rust-demangle.c" \
        "${REPO}/libiberty/safe-ctype.c" \
        -lpthread -lm \
        -o "${OUT}/harness"

    echo "built ${OUT}/harness ($(stat -c %s "${OUT}/harness") bytes)"
    exit 0
fi
exit 2
