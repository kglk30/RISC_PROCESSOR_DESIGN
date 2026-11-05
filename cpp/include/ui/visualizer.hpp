#pragma once

#include <string>
#include <unordered_map>
#include "core/memory.hpp"
#include "core/registers.hpp"

namespace risc201 {

class Visualizer {
public:
    static std::string render_stack(const Memory& memory, const RegisterFile& rf, int max_words_above_fp = 4);
    static std::string render_pipeline_4stage(const std::unordered_map<std::string, std::string>& stages, uint64_t cycle);
    static std::string render_pipeline_6stage(const std::unordered_map<std::string, std::string>& stages, uint64_t cycle);
};

} // namespace risc201
