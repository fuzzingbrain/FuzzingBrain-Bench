#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <ldap.h>
#include <ldap_schema.h>

static const unsigned int flags[] = {
    LDAP_SCHEMA_ALLOW_NONE,
    LDAP_SCHEMA_ALLOW_NO_OID,
    LDAP_SCHEMA_ALLOW_QUOTED,
    LDAP_SCHEMA_ALLOW_DESCR,
    LDAP_SCHEMA_ALLOW_ALL,
};

#define NUM_FLAGS (sizeof(flags) / sizeof(flags[0]))

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size == 0 || size > 16384) return 0;

    char *input = (char *)malloc(size + 1);
    if (!input) return 0;
    memcpy(input, data, size);
    input[size] = '\0';

    int code = 0;
    const char *errp = NULL;

    for (size_t i = 0; i < NUM_FLAGS; i++) {
        code = 0;
        errp = NULL;
        LDAPAttributeType *at = ldap_str2attributetype(input, &code,
                                                        &errp, flags[i]);
        if (at) {
            ldap_attributetype_free(at);
        }
    }

    for (size_t i = 0; i < NUM_FLAGS; i++) {
        code = 0;
        errp = NULL;
        LDAPObjectClass *oc = ldap_str2objectclass(input, &code,
                                                     &errp, flags[i]);
        if (oc) {
            ldap_objectclass_free(oc);
        }
    }

    free(input);
    return 0;
}
