#include <gssapi/gssapi.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 1) return 0;

    gss_buffer_desc input_name_buffer;
    input_name_buffer.length = size;
    input_name_buffer.value = (void *)data;

    gss_OID name_type = (data[0] & 1) ? GSS_C_NT_COMPOSITE_EXPORT : GSS_C_NT_EXPORT_NAME;
    gss_name_t output_name = GSS_C_NO_NAME;
    OM_uint32 major, minor;

    major = gss_import_name(&minor, &input_name_buffer, name_type, &output_name);
    if (major == GSS_S_COMPLETE) {
        gss_release_name(&minor, &output_name);
    }

    return 0;
}

#if defined(MAIN)
int main(int argc, char *argv[]) {
    if (argc > 1) {
        FILE *f = fopen(argv[1], "rb");
        if (f) {
            fseek(f, 0, SEEK_END);
            long len = ftell(f);
            fseek(f, 0, SEEK_SET);
            if (len > 0) {
                uint8_t *buf = malloc(len);
                if (buf) {
                    size_t read_len = fread(buf, 1, len, f);
                    LLVMFuzzerTestOneInput(buf, read_len);
                    free(buf);
                }
            }
            fclose(f);
        }
    }
    return 0;
}
#endif
