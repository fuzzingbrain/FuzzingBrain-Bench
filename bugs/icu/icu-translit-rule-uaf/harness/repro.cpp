#include "unicode/translit.h"
#include "unicode/unistr.h"
#include "unicode/parseerr.h"
#include "unicode/utypes.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <vector>

int main(int argc, char* argv[]) {
    std::ifstream file(argv[1], std::ios::binary);
    std::vector<uint8_t> data((std::istreambuf_iterator<char>(file)),
                               std::istreambuf_iterator<char>());
    if (data.size() < 3) return 1;

    uint8_t dir = data[0] & 1;
    size_t unistr_size = (data.size() - 1) / 2;
    std::vector<char16_t> buf(unistr_size);
    memcpy(buf.data(), data.data() + 1, unistr_size * 2);
    icu::UnicodeString rules(false, buf.data(), unistr_size);

    UErrorCode status = U_ZERO_ERROR;
    UParseError pe;
    icu::Transliterator* t = icu::Transliterator::createFromRules(
        UNICODE_STRING_SIMPLE("test"), rules,
        dir ? UTRANS_FORWARD : UTRANS_REVERSE, pe, status);

    if (U_SUCCESS(status) && t) {
        icu::UnicodeString sample(u"Hello");
        t->transliterate(sample);
        delete t;
    }
    return 0;
}
