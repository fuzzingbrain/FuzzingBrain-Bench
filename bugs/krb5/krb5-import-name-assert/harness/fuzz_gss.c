/* -*- mode: c; c-basic-offset: 4; indent-tabs-mode: nil -*- */
/* LibFuzzer harness for gss_import_name exported-name parsing. */

#include "autoconf.h"

#include <stddef.h>
#include <stdint.h>

#include <gssapi.h>
#include <gssapi/gssapi_ext.h>

#define kMinInputLength 1
#define kMaxInputLength 4096

extern int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);

int
LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    OM_uint32 major, minor;
    gss_buffer_desc input_name_buffer;
    gss_name_t output_name = GSS_C_NO_NAME;
    gss_OID name_type;

    if (size < kMinInputLength || size > kMaxInputLength)
        return 0;

    input_name_buffer.length = size;
    input_name_buffer.value = (void *)data;

    /* Exercise the exported-name parser in the mechglue import path. */
    name_type = (data[0] & 1) ? GSS_C_NT_COMPOSITE_EXPORT : GSS_C_NT_EXPORT_NAME;

    major = gss_import_name(&minor, &input_name_buffer, name_type, &output_name);
    if (major == GSS_S_COMPLETE)
        (void)gss_release_name(&minor, &output_name);

    return 0;
}
