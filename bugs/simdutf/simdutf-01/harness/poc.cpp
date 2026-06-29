#include "simdutf.h"

int main() {
    // 'é' (2 UTF-8 bytes) + 'A' (1 UTF-8 byte) = 3 bytes needed
    char16_t input[] = {0x00E9, 'A'};
    char output[2];  // Only 2 bytes buffer

    // API says utf8_len is "the maximum output length"

    size_t written = simdutf::convert_utf16_to_utf8_safe(
        input, 2, output, 2);

    // written == 3, violating the API contract
    return 0;
}
