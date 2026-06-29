#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <ldap.h>
#include <ldap_schema.h>

int main(int argc, char **argv) {
    FILE *f = fopen("poc", "rb");
    fseek(f, 0, SEEK_END);
    long size = ftell(f);
    fseek(f, 0, SEEK_SET);

    char *input = malloc(size + 1);
    fread(input, 1, size, f);
    input[size] = '\0';
    fclose(f);

    int code = 0;
    const char *errp = NULL;

    LDAPAttributeType *at = ldap_str2attributetype(input, &code,
                                                     &errp, LDAP_SCHEMA_ALLOW_ALL);
    if (at) {
        ldap_attributetype_free(at);
    }

    free(input);
    return 0;
}
