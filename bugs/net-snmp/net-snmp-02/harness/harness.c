#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <net-snmp/net-snmp-config.h>
#include <net-snmp/net-snmp-includes.h>
#include <net-snmp/library/vacm.h>

static int initialized = 0;

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (!initialized) {
        init_snmp("vacm_fuzzer");
        initialized = 1;
    }

    if (size == 0 || size > 4096) return 0;

    char *line = (char *)malloc(size + 1);
    if (!line) return 0;
    memcpy(line, data, size);
    line[size] = '\0';


    vacm_parse_config_group("vacmGroup", line);

    free(line);
    return 0;
}
