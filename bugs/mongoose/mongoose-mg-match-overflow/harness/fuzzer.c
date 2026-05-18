/**
 * Fuzzer for mongoose mg_match pattern matching
 * Build: clang -fsanitize=fuzzer,address -g -I. fuzzer.c -o fuzz_match
 */
#define MG_ENABLE_SOCKET 0
#define MG_ENABLE_LOG 0
#include "mongoose.c"

static void fuzz_match_patterns(const uint8_t *data, size_t size) {
    if (size < 2) return;

    // Split data into pattern and string
    size_t split = size / 2;
    struct mg_str pattern = mg_str_n((const char *)data, split);
    struct mg_str str = mg_str_n((const char *)data + split, size - split);

    struct mg_str caps[10];
    memset(caps, 0, sizeof(caps));

    mg_match(str, pattern, caps);  // Triggers vulnerability
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
    if (size < 2) return 0;
    fuzz_match_patterns(data, size);
    return 0;
}

#if defined(MAIN)
int main(int argc, char *argv[]) {
    if (argc > 1) {
        struct mg_str data = mg_file_read(&mg_fs_posix, argv[1]);
        if (data.buf != NULL) {
            LLVMFuzzerTestOneInput((uint8_t *)data.buf, data.len);
            free(data.buf);
        }
    }
    return 0;
}
#endif
