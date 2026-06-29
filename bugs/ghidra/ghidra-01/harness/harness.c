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
