#include <stddef.h>
#include <stdint.h>
#include <cstring>
#include <memory>

#include "unicode/translit.h"
#include "unicode/unistr.h"
#include "unicode/parseerr.h"
#include "unicode/utypes.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    if (size < 3) return 0;

    uint8_t dir = data[0] & 1;
    data++;
    size--;

    size_t unistr_size = size / 2;
    std::unique_ptr<char16_t[]> fuzzbuff(new char16_t[unistr_size]);
    std::memcpy(fuzzbuff.get(), data, unistr_size * 2);
    icu::UnicodeString fuzzstr(false, fuzzbuff.get(), unistr_size);

    UErrorCode status = U_ZERO_ERROR;
    UParseError pe;
    std::unique_ptr<icu::Transliterator> t(
        icu::Transliterator::createFromRules(
            UNICODE_STRING_SIMPLE("fuzz"), fuzzstr,
            dir ? UTRANS_FORWARD : UTRANS_REVERSE, pe, status));

    if (U_SUCCESS(status) && t) {

        icu::UnicodeString sample(u"Hello World 123");
        t->transliterate(sample);

        // Transliterate the fuzz input itself
        icu::UnicodeString input(fuzzstr);
        t->transliterate(input);
    }

    return 0;
}
