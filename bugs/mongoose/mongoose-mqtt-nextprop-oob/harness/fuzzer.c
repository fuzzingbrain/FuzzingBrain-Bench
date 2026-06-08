/**
 * Fuzzer for mongoose MQTT5 property parsing (mg_mqtt_parse -> mg_mqtt_next_prop).
 * Models a client/server that parses an MQTT5 packet and iterates its properties.
 * Build: clang -fsanitize=fuzzer,address -g -I. fuzzer.c -o fuzz_mqtt
 */
#define MG_ENABLE_SOCKET 0
#define MG_ENABLE_LOG 0
#include "mongoose.c"

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    struct mg_mqtt_message mm;
    if (mg_mqtt_parse(data, size, 5, &mm) == MQTT_OK) {
        struct mg_mqtt_prop prop;
        size_t ofs = 0;
        int count = 0;
        while ((ofs = mg_mqtt_next_prop(&mm, &prop, ofs)) > 0) {
            (void) prop.id;
            (void) prop.iv;
            if (prop.key.len > 0 && prop.key.buf) (void) prop.key.buf[0];
            if (prop.val.len > 0 && prop.val.buf) (void) prop.val.buf[0];
            if (++count > 1000) break;
        }
    }
    return 0;
}

#if defined(MAIN)
int main(int argc, char *argv[]) {
    if (argc > 1) {
        struct mg_str d = mg_file_read(&mg_fs_posix, argv[1]);
        if (d.buf) { LLVMFuzzerTestOneInput((uint8_t *) d.buf, d.len); free(d.buf); }
    }
    return 0;
}
#endif
