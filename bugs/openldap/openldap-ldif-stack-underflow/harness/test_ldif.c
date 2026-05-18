#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ldap.h>
#include <ldif.h>
#include <lber.h>

int main(int argc, char **argv) {
    FILE *f = fopen("poc", "rb");
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *input = malloc(size + 1);
    fread(input, 1, size, f);
    input[size] = '\0';
    fclose(f);
    LDIFFP *fp = ldif_open_mem(input, size, "r");
    if (fp) {
        unsigned long lineno = 0;
        char *buf = NULL;
        int buflen = 0;
        ldif_read_record(fp, &lineno, &buf, &buflen);
        if (buf) ber_memfree(buf);
        ldif_close(fp);
    }
    free(input);
    return 0;
}
