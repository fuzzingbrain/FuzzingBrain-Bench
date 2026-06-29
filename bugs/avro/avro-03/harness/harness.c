#include <stdint.h>
#include <stddef.h>
#include <string.h>

#include <avro.h>

/* Predefined schemas for fuzzing */
static const char *SCHEMAS[] = {
    /* Primitive types */
    "\"null\"",
    "\"boolean\"",
    "\"int\"",
    "\"long\"",
    "\"float\"",
    "\"double\"",
    "\"bytes\"",
    "\"string\"",

    /* Array types */
    "{\"type\": \"array\", \"items\": \"int\"}",
    "{\"type\": \"array\", \"items\": \"string\"}",
    "{\"type\": \"array\", \"items\": \"bytes\"}",

    /* Map types */
    "{\"type\": \"map\", \"values\": \"int\"}",
    "{\"type\": \"map\", \"values\": \"string\"}",

    /* Record types */
    "{\"type\": \"record\", \"name\": \"TestRecord\", \"fields\": ["
        "{\"name\": \"f1\", \"type\": \"int\"},"
        "{\"name\": \"f2\", \"type\": \"string\"}"
    "]}",

    /* Nested record */
    "{\"type\": \"record\", \"name\": \"Outer\", \"fields\": ["
        "{\"name\": \"inner\", \"type\": {"
            "\"type\": \"record\", \"name\": \"Inner\", \"fields\": ["
                "{\"name\": \"value\", \"type\": \"long\"}"
            "]"
        "}}"
    "]}",

    /* Enum type */
    "{\"type\": \"enum\", \"name\": \"Color\", \"symbols\": [\"RED\", \"GREEN\", \"BLUE\"]}",

    
    "{\"type\": \"fixed\", \"name\": \"Hash\", \"size\": 16}",

    /* Union types */
    "[\"null\", \"string\"]",
    "[\"null\", \"int\", \"long\", \"string\"]",

    /* Complex nested type */
    "{\"type\": \"record\", \"name\": \"Complex\", \"fields\": ["
        "{\"name\": \"id\", \"type\": \"long\"},"
        "{\"name\": \"name\", \"type\": [\"null\", \"string\"]},"
        "{\"name\": \"tags\", \"type\": {\"type\": \"array\", \"items\": \"string\"}},"
        "{\"name\": \"metadata\", \"type\": {\"type\": \"map\", \"values\": \"bytes\"}}"
    "]}"
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
