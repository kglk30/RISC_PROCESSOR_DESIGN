#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace risc201 {

class Disassembler {
public:
    static std::string reg_name(uint8_t reg_idx);
    static std::string disassemble_word(uint32_t word, uint32_t current_pc = 0);
    static std::string disassemble_hex(const std::string& hex_str, uint32_t current_pc = 0);
    static std::vector<std::string> disassemble_words(const std::vector<int32_t>& words, uint32_t start_pc = 0);
};

} // namespace risc201
