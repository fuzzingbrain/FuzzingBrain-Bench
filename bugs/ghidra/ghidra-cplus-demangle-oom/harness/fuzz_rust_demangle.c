/*
 * Fuzzer for Rust Symbol Demangler
 *
 * Target: GPL/DemanglerGnu/src/demangler_gnu_v2_41/c/rust-demangle.c
 * Entry point: rust_demangle() - Rust symbol demangling function
 *
 * Rust symbols have two formats:
 * - Legacy: _ZN...E (similar to C++ but with hash suffix like 17h...)
 * - v0: _R... (new format with uppercase letters)
 *
 * This fuzzer tests both formats by passing arbitrary data.
 * The demangler validates the prefix and format internally.
 *
 * Build:
 *   clang -g -O1 -fno-omit-frame-pointer -fsanitize=fuzzer,address \
 *     -I<path>/headers fuzz_rust_demangle.c rust-demangle.c \
 *     safe-ctype.c -o fuzz_rust_demangle
 */

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "demangle.h"

/* Standard flags - DMGL_VERBOSE shows hash in output */
#define DEFAULT_FLAGS (DMGL_VERBOSE)

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    /* Skip empty inputs */
    if (size == 0) {
        return 0;
    }

    /* Allocate buffer and ensure null-termination */
    char *mangled = (char *)malloc(size + 1);
    if (mangled == NULL) {
        return 0;
    }

    memcpy(mangled, data, size);
    mangled[size] = '\0';

    /* Call the Rust demangler */
    char *result = rust_demangle(mangled, DEFAULT_FLAGS);

    /* Free the result if demangling succeeded */
    if (result != NULL) {
        free(result);
    }

    free(mangled);
    return 0;
}
