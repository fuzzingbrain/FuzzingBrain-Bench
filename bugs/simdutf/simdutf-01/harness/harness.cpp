#include <cstddef>
#include <cstdint>
#include <cstring>
#include <vector>
#include <algorithm>
#include "simdutf.h"

constexpr size_t MAX_INPUT_SIZE = 64 * 1024;
constexpr size_t MAX_OUTPUT_SIZE = 4 * 1024 * 1024;

struct FuzzReader {
    const uint8_t* data;
    size_t size;
    size_t pos = 0;

    explicit FuzzReader(const uint8_t* d, size_t s) : data(d), size(s) {}

    uint8_t read_u8() {
        if (pos >= size) return 0;
        return data[pos++];
    }

    uint16_t read_u16() {
        if (pos + 2 > size) return 0;
        uint16_t val = data[pos] | (data[pos + 1] << 8);
        pos += 2;
        return val;
    }

    const char* get_char_data() const {
        return reinterpret_cast<const char*>(data + pos);
    }

    size_t remaining() const {
        return (pos < size) ? (size - pos) : 0;
    }
};


void fuzz_convert_utf16_to_utf8_safe(const std::vector<char16_t>& input,
                                      size_t output_limit) {
    if (input.empty()) return;

    size_t expected_len = simdutf::utf8_length_from_utf16(input.data(), input.size());
    if (expected_len == 0 || expected_len > MAX_OUTPUT_SIZE) return;

    size_t actual_limit = std::min(output_limit, expected_len + 1);
    if (actual_limit == 0) actual_limit = 1;

    std::vector<char> output(actual_limit);

    size_t written = simdutf::convert_utf16_to_utf8_safe(
        input.data(), input.size(), output.data(), actual_limit);

    // Key check: written must not exceed actual_limit
    if (written > actual_limit) {
        __builtin_trap();
    }
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    if (size < 4) return 0;

    FuzzReader reader(data, size);
    uint8_t test_case = reader.read_u8();
    reader.read_u8();  // needle_byte (unused here)
    uint16_t limit_mod = reader.read_u16();

    const char* char_input = reader.get_char_data();
    size_t char_len = reader.remaining();
    if (char_len == 0 || char_len > MAX_INPUT_SIZE) return 0;

    size_t char16_count = char_len / sizeof(char16_t);
    std::vector<char16_t> char16_input;
    if (char16_count > 0) {
        char16_input.resize(char16_count);
        std::memcpy(char16_input.data(), char_input, char16_count * sizeof(char16_t));
    }

    size_t output_limit = (limit_mod == 0) ? 1 : (limit_mod * 64);
    if (output_limit > MAX_OUTPUT_SIZE) output_limit = MAX_OUTPUT_SIZE;

    if (test_case % 5 == 3 && !char16_input.empty()) {
        fuzz_convert_utf16_to_utf8_safe(char16_input, output_limit);
    }

    return 0;
}
