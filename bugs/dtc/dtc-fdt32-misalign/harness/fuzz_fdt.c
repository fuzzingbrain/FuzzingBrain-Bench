// fuzz_fdt.c
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include "libfdt.h"

#define MAX_DEPTH 64

static void traverse_nodes(const void *fdt, int offset, int depth) {
    if (depth > MAX_DEPTH) return;

    int subnode_offset;
    fdt_for_each_subnode(subnode_offset, fdt, offset) {
        const char *name = fdt_get_name(fdt, subnode_offset, NULL);
        (void)name;

        int prop_offset;
        fdt_for_each_property_offset(prop_offset, fdt, subnode_offset) {
            const char *prop_name;
            int len;
            const void *prop_data = fdt_getprop_by_offset(fdt, prop_offset,
                                                          &prop_name, &len);
            (void)prop_data;
        }
        traverse_nodes(fdt, subnode_offset, depth + 1);
    }
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < FDT_V1_SIZE || size > 8 * 1024 * 1024)
        return 0;

    void *fdt = malloc(size);
    if (!fdt) return 0;
    memcpy(fdt, data, size);

    if (fdt_check_header(fdt) != 0) {
        free(fdt);
        return 0;
    }

    // Path lookups
    fdt_path_offset(fdt, "/");
    fdt_path_offset(fdt, "/chosen");

    // Node traversal - triggers the bug
    traverse_nodes(fdt, 0, 0);

    free(fdt);
    return 0;
}
