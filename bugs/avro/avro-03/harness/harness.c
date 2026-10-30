#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include <avro.h>

/* A single schema; every input is decoded against it. */
static const char *SCHEMAS[] = {
    "{\"type\": \"map\", \"values\": \"string\"}",
};

static const size_t NUM_SCHEMAS = sizeof(SCHEMAS) / sizeof(SCHEMAS[0]);

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 1) {
        return 0;
    }

    /* Use first byte to select schema */
    size_t schema_idx = data[0] % NUM_SCHEMAS;
    const char *schema_json = SCHEMAS[schema_idx];

    const uint8_t *binary_data = data + 1;
    size_t binary_size = size - 1;

    if (binary_size == 0) {
        return 0;
    }

    avro_schema_t schema = NULL;
    avro_value_iface_t *iface = NULL;
    avro_value_t value;
    avro_reader_t reader = NULL;
    int rc;

    rc = avro_schema_from_json_length(schema_json, strlen(schema_json), &schema);
    if (rc != 0 || schema == NULL) {
        return 0;
    }

    iface = avro_generic_class_from_schema(schema);
    if (iface == NULL) {
        avro_schema_decref(schema);
        return 0;
    }

    memset(&value, 0, sizeof(value));
    rc = avro_generic_value_new(iface, &value);
    if (rc != 0) {
        avro_value_iface_decref(iface);
        avro_schema_decref(schema);
        return 0;
    }

    reader = avro_reader_memory((const char *)binary_data, binary_size);
    if (reader == NULL) {
        avro_value_decref(&value);
        avro_value_iface_decref(iface);
        avro_schema_decref(schema);
        return 0;
    }

    
    rc = avro_value_read(reader, &value);
    (void)rc;

    avro_reader_free(reader);
    avro_value_decref(&value);
    avro_value_iface_decref(iface);
    avro_schema_decref(schema);

    return 0;
}
