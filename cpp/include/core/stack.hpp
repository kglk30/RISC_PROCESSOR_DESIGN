#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace risc201 {

constexpr int32_t DEFAULT_CANARY = 0x1C0DE;
constexpr int32_t CANARY_MAGIC   = 0x1C0DE;

class StackPreprocessor {
public:
    int32_t canary;
    int label_counter{0};
    bool optimize_leaf{false};

    explicit StackPreprocessor(int32_t can = CANARY_MAGIC, bool opt_leaf = false);
    std::vector<std::string> expand_lines(const std::vector<std::string>& lines);
};

} // namespace risc201
