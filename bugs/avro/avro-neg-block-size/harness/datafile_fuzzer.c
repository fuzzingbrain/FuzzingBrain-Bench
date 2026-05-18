/*
 * Copyright 2026 O2Lab @ Texas A&M University
 *
 * Fuzzer for Avro C DataFile Reader
 * Target: avro_file_reader_fp() and avro_file_reader_read_value()
 */

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

#include <avro.h>

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 4) {
        return 0;
    }

    /* Write fuzz data to a temporary file */
    char template[] = "/tmp/avro_fuzz_XXXXXX";
    int fd = mkstemp(template);
    if (fd < 0) {
        return 0;
    }

    ssize_t written = write(fd, data, size);
    if (written != (ssize_t)size) {
        close(fd);
        unlink(template);
        return 0;
    }

    lseek(fd, 0, SEEK_SET);

    FILE *fp = fdopen(fd, "rb");
    if (fp == NULL) {
        close(fd);
        unlink(template);
        return 0;
    }

    avro_file_reader_t reader = NULL;
    avro_value_iface_t *iface = NULL;
    avro_value_t value;
    int rc;

    rc = avro_file_reader_fp(fp, template, 0, &reader);
    if (rc != 0 || reader == NULL) {
        fclose(fp);
        unlink(template);
        return 0;
    }

    avro_schema_t schema = avro_file_reader_get_writer_schema(reader);
    if (schema == NULL) {
        avro_file_reader_close(reader);
        fclose(fp);
        unlink(template);
        return 0;
    }

    iface = avro_generic_class_from_schema(schema);
    if (iface == NULL) {
        avro_schema_decref(schema);
        avro_file_reader_close(reader);
        fclose(fp);
        unlink(template);
        return 0;
    }

    memset(&value, 0, sizeof(value));
    rc = avro_generic_value_new(iface, &value);
    if (rc != 0) {
        avro_value_iface_decref(iface);
        avro_schema_decref(schema);
        avro_file_reader_close(reader);
        fclose(fp);
        unlink(template);
        return 0;
    }

    /* Read up to 100 values */
    for (int i = 0; i < 100; i++) {
        rc = avro_file_reader_read_value(reader, &value);
        if (rc != 0) {
            break;
        }
        avro_value_reset(&value);
    }

    avro_value_decref(&value);
    avro_value_iface_decref(iface);
    avro_schema_decref(schema);
    avro_file_reader_close(reader);
    fclose(fp);
    unlink(template);

    return 0;
}
