#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <unordered_map>
#include "core/stack.hpp"

namespace risc201 {

struct AssembledProgram {
    std::vector<int32_t> text_words;
    uint32_t text_start_addr{0x00000000};
    std::vector<uint8_t> data_bytes;
    uint32_t data_start_addr{0x00001000};
    std::unordered_map<std::string, uint32_t> symbol_table;
    std::unordered_map<uint32_t, std::string> source_map;
    std::vector<std::string> listing;

    std::vector<std::string> to_hex_lines() const;
};

class Assembler {
public:
    StackPreprocessor preprocessor;

    explicit Assembler(int32_t canary = CANARY_MAGIC, bool optimize_leaf = false);
    AssembledProgram assemble(const std::string& source_text);

private:
    uint32_t calc_data_size(const std::string& line);
    std::vector<uint8_t> assemble_data(const std::string& line, const std::unordered_map<std::string, uint32_t>& symbols);
    uint32_t assemble_instruction(const std::string& line, uint32_t pc, const std::unordered_map<std::string, uint32_t>& symbols);
    uint8_t parse_reg(const std::string& token);
    int32_t parse_int(const std::string& token, const std::unordered_map<std::string, uint32_t>& symbols);
};

} // namespace risc201
