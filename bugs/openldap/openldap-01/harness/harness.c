#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <ldap.h>
#include <ldif.h>
#include <lber.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size == 0 || size > 65536) return 0;
    char *input = (char *)malloc(size + 1);
    if (!input) return 0;
    memcpy(input, data, size);
    input[size] = '\0';
    char *mem_copy = (char *)malloc(size + 1);
    if (mem_copy) {
        memcpy(mem_copy, data, size);
        mem_copy[size] = '\0';
        LDIFFP *fp = ldif_open_mem(mem_copy, size, "r");
        if (fp) {
            unsigned long lineno = 0;
            char *buf = NULL;
            int buflen = 0;
            int count = 0;
            while (count < 100) {
                int rc = ldif_read_record(fp, &lineno, &buf, &buflen);
                if (rc <= 0) break;
                count++;
            }
            if (buf) ber_memfree(buf);
            ldif_close(fp);
        }
        free(mem_copy);
    }
    free(input);
    return 0;
}
