#include <hunspell/hunspell.hxx>

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

#include <fuzzer/FuzzedDataProvider.h>

namespace {

std::string g_workspace;



// that actually resolve.
constexpr const char kAffPrefix[] =
    "SET UTF-8\n"
    "FLAG long\n"
    "TRY abcdefghijklmnopqrstuvwxyz\n";

class ScopedTmpFile {
   public:
    ScopedTmpFile() = default;
    ~ScopedTmpFile() {
        if (!path_.empty()) {
            ::unlink(path_.c_str());
        }
    }
    ScopedTmpFile(const ScopedTmpFile&) = delete;
    ScopedTmpFile& operator=(const ScopedTmpFile&) = delete;

    bool Create(const char* suffix, const uint8_t* bytes, size_t len) {
        std::string tmpl = g_workspace + "/dic_harness_XXXXXX";
        std::vector<char> buf(tmpl.begin(), tmpl.end());
        buf.push_back('\0');
        int fd = ::mkstemp(buf.data());
        if (fd < 0) {
            return false;
        }
        std::string raw(buf.data());
        std::string final_path = raw + suffix;
        if (::rename(raw.c_str(), final_path.c_str()) != 0) {
            ::close(fd);
            ::unlink(raw.c_str());
            return false;
        }
        path_ = final_path;
        ssize_t want = static_cast<ssize_t>(len);
        ssize_t off = 0;
        while (off < want) {
            ssize_t n = ::write(fd, bytes + off, want - off);
            if (n <= 0) {
                ::close(fd);
                return false;
            }
            off += n;
        }
        ::close(fd);
        return true;
    }

    const std::string& path() const { return path_; }

   private:
    std::string path_;
};

}  // namespace

extern "C" int LLVMFuzzerInitialize(int* /*argc*/, char*** /*argv*/) {
    const char* env = ::getenv("O2_HUNSPELL_FUZZ_WORKDIR");
    if (env && *env) {
        g_workspace = env;
    } else {
        g_workspace = "/tmp/hunspell_fuzz_workdir";
    }
    struct stat st;
    if (::stat(g_workspace.c_str(), &st) != 0) {
        ::mkdir(g_workspace.c_str(), 0755);
    }
    return 0;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    if (size < 8 || size > 32768) {
        return 0;
    }

    FuzzedDataProvider fdp(data, size);

    // Layout:
    //   [aff_alias_block] [dic_primary] [dic_custom] [word_bytes]
    // with the aff alias block and dic_primary each sized from fuzz
    // input via ConsumeIntegralInRange.
    size_t remaining = fdp.remaining_bytes();
    size_t alias_len =
        fdp.ConsumeIntegralInRange<size_t>(0, remaining > 16 ? remaining / 4 : remaining);
    std::vector<uint8_t> alias_block = fdp.ConsumeBytes<uint8_t>(alias_len);

    remaining = fdp.remaining_bytes();
    size_t primary_len =
        fdp.ConsumeIntegralInRange<size_t>(0, remaining > 16 ? remaining / 2 : remaining);
    std::vector<uint8_t> primary_dic = fdp.ConsumeBytes<uint8_t>(primary_len);

    remaining = fdp.remaining_bytes();
    size_t custom_len =
        fdp.ConsumeIntegralInRange<size_t>(0, remaining > 8 ? remaining / 2 : remaining);
    std::vector<uint8_t> custom_dic = fdp.ConsumeBytes<uint8_t>(custom_len);

    std::vector<uint8_t> word_bytes = fdp.ConsumeRemainingBytes<uint8_t>();


    std::vector<uint8_t> aff_bytes;
    aff_bytes.insert(aff_bytes.end(),
                     reinterpret_cast<const uint8_t*>(kAffPrefix),
                     reinterpret_cast<const uint8_t*>(kAffPrefix) +
                         sizeof(kAffPrefix) - 1);
    aff_bytes.insert(aff_bytes.end(), alias_block.begin(), alias_block.end());
    if (!aff_bytes.empty() && aff_bytes.back() != '\n') {
        aff_bytes.push_back('\n');
    }

    ScopedTmpFile aff_file;
    ScopedTmpFile dic_primary_file;
    ScopedTmpFile dic_custom_file;
    if (!aff_file.Create(".aff", aff_bytes.data(), aff_bytes.size())) {
        return 0;
    }
    // Primary .dic MUST exist; if fuzz slice is empty, emit a tiny
    // valid body so the ctor path runs and add_dic has something to
    // stack onto.
    if (primary_dic.empty()) {
        static const uint8_t kMinimal[] = "1\nhello\n";
        primary_dic.assign(kMinimal, kMinimal + sizeof(kMinimal) - 1);
    }
    if (!dic_primary_file.Create(".dic", primary_dic.data(), primary_dic.size())) {
        return 0;
    }
    // Custom .dic — optional, only created if the fuzz slice has
    // content. add_dic on a missing file is a documented error path;
    // we exercise both the "stacked second dic" and the "ctor only"
    // cases depending on fuzz input.
    bool have_custom = !custom_dic.empty();
    if (have_custom) {
        if (!dic_custom_file.Create(".dic", custom_dic.data(), custom_dic.size())) {
            return 0;
        }
    }

    try {
        Hunspell dict(aff_file.path().c_str(), dic_primary_file.path().c_str());

        if (have_custom) {
            // add_dic returns 0 on success, non-zero on parse failure.
            // Ignore the return — we care about the side effects
            // (memory safety), not success status.
            (void)dict.add_dic(dic_custom_file.path().c_str());
        }

        constexpr int kMaxWordsPerIter = 8;
        int words_tried = 0;
        size_t cursor = 0;
        while (cursor < word_bytes.size() && words_tried < kMaxWordsPerIter) {
            size_t end = cursor;
            while (end < word_bytes.size() && word_bytes[end] != '\n' &&
                   (end - cursor) < 64) {
                ++end;
            }
            if (end > cursor) {
                std::string word(reinterpret_cast<const char*>(&word_bytes[cursor]),
                                 end - cursor);
                int info = 0;
                std::string root;
                (void)dict.spell(word, &info, &root);
                ++words_tried;
            }
            cursor = end;
            while (cursor < word_bytes.size() && word_bytes[cursor] != '\n') {
                ++cursor;
            }
            if (cursor < word_bytes.size()) {
                ++cursor;
            }
        }
    } catch (...) {
        // Swallow std::bad_alloc from adversarial .dic count headers.
    }

    return 0;
}

/* vim:set shiftwidth=4 softtabstop=4 expandtab: */
