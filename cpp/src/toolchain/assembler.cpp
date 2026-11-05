#include "toolchain/assembler.hpp"
#include "core/isa.hpp"
#include <sstream>
#include <algorithm>
#include <iomanip>
#include <regex>
#include <stdexcept>

namespace risc201 {

static std::string trim(const std::string& str) {
    size_t first = str.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) return "";
    size_t last = str.find_last_not_of(" \t\r\n");
    return str.substr(first, (last - first + 1));
}

Assembler::Assembler(int32_t canary, bool optimize_leaf) : preprocessor(canary, optimize_leaf) {}

std::vector<std::string> AssembledProgram::to_hex_lines() const {
    std::vector<std::string> lines;
    for (size_t i = 0; i < text_words.size(); ++i) {
        uint32_t addr = text_start_addr + static_cast<uint32_t>(i * 4);
        uint32_t u32 = static_cast<uint32_t>(text_words[i]);
        std::stringstream ss;
        ss << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << addr
           << ": 0x" << std::setw(8) << u32;
        auto it = source_map.find(addr);
        if (it != source_map.end()) {
            ss << "    ; " << it->second;
        }
        lines.push_back(ss.str());
    }
    return lines;
}

uint32_t Assembler::calc_data_size(const std::string& line) {
    std::stringstream ss(line);
    std::string directive;
    ss >> directive;
    std::transform(directive.begin(), directive.end(), directive.begin(), ::tolower);

    std::string args;
    std::getline(ss, args);
    args = trim(args);

    if (directive == ".word") {
        std::stringstream ss_args(args);
        std::string token;
        int count = 0;
        while (std::getline(ss_args, token, ',')) {
            if (!trim(token).empty()) count++;
        }
        return count * 4;
    } else if (directive == ".space") {
        return std::stoul(args, nullptr, 0);
    } else if (directive == ".asciiz") {
        std::regex re(R"(\"(.*)\")");
        std::smatch match;
        if (std::regex_search(args, match, re)) {
            return static_cast<uint32_t>(match.str(1).length() + 1);
        }
        return 1;
    }
    return 0;
}

std::vector<uint8_t> Assembler::assemble_data(const std::string& line, const std::unordered_map<std::string, uint32_t>& symbols) {
    std::vector<uint8_t> out;
    std::stringstream ss(line);
    std::string directive;
    ss >> directive;
    std::transform(directive.begin(), directive.end(), directive.begin(), ::tolower);

    std::string args;
    std::getline(ss, args);
    args = trim(args);

    if (directive == ".word") {
        std::stringstream ss_args(args);
        std::string token;
        while (std::getline(ss_args, token, ',')) {
            std::string t = trim(token);
            if (t.empty()) continue;
            uint32_t val = 0;
            auto it = symbols.find(t);
            if (it != symbols.end()) {
                val = it->second;
            } else {
                val = static_cast<uint32_t>(std::stol(t, nullptr, 0));
            }
            out.push_back(static_cast<uint8_t>(val & 0xFF));
            out.push_back(static_cast<uint8_t>((val >> 8) & 0xFF));
            out.push_back(static_cast<uint8_t>((val >> 16) & 0xFF));
            out.push_back(static_cast<uint8_t>((val >> 24) & 0xFF));
        }
    } else if (directive == ".space") {
        size_t count = std::stoul(args, nullptr, 0);
        out.assign(count, 0);
    } else if (directive == ".asciiz") {
        std::regex re(R"(\"(.*)\")");
        std::smatch match;
        if (std::regex_search(args, match, re)) {
            std::string str_val = match.str(1);
            out.insert(out.end(), str_val.begin(), str_val.end());
            out.push_back(0);
        }
    }

    return out;
}

uint8_t Assembler::parse_reg(const std::string& token) {
    auto reg_opt = parse_register_alias(token);
    if (!reg_opt) {
        throw std::runtime_error("Unknown register name: '" + token + "'");
    }
    return *reg_opt;
}

int32_t Assembler::parse_int(const std::string& token, const std::unordered_map<std::string, uint32_t>& symbols) {
    std::string t = trim(token);
    auto it = symbols.find(t);
    if (it != symbols.end()) {
        return static_cast<int32_t>(it->second);
    }
    return static_cast<int32_t>(std::stol(t, nullptr, 0));
}

uint32_t Assembler::assemble_instruction(const std::string& line, uint32_t pc, const std::unordered_map<std::string, uint32_t>& symbols) {
    std::stringstream ss(line);
    std::string mnemonic;
    ss >> mnemonic;
    std::string rest;
    std::getline(ss, rest);

    std::vector<std::string> args;
    std::stringstream ss_args(rest);
    std::string token;
    while (std::getline(ss_args, token, ',')) {
        std::string t = trim(token);
        if (!t.empty()) args.push_back(t);
    }

    auto op_opt = parse_opcode(mnemonic);
    if (!op_opt) {
        throw std::runtime_error("Unknown instruction mnemonic: '" + mnemonic + "'");
    }
    Opcode op = *op_opt;

    if (op == Opcode::NOP || op == Opcode::HLT || op == Opcode::RET) {
        DecodedInstruction inst;
        inst.opcode = op;
        return encode_instruction(inst);
    }

    if (op == Opcode::TRAP) {
        DecodedInstruction inst;
        inst.opcode = op;
        inst.trap_id = args.empty() ? 0 : parse_int(args[0], symbols);
        return encode_instruction(inst);
    }

    if (is_branch_op(op)) {
        std::string target = args[0];
        int32_t offset = 0;
        auto it = symbols.find(target);
        if (it != symbols.end()) {
            offset = static_cast<int32_t>((it->second - pc) / 4);
        } else {
            offset = parse_int(target, symbols);
        }
        DecodedInstruction inst;
        inst.opcode = op;
        inst.offset = offset;
        return encode_instruction(inst);
    }

    if (op == Opcode::LD || op == Opcode::ST) {
        uint8_t rd = parse_reg(args[0]);
        std::string mem_op = args[1];
        std::regex re(R"(^([^\[]*)\[([^\]]+)\]$)");
        std::smatch match;
        int32_t imm = 0;
        uint8_t rs1 = 0;
        if (std::regex_match(mem_op, match, re)) {
            std::string off_str = trim(match.str(1));
            std::string rs1_str = trim(match.str(2));
            imm = off_str.empty() ? 0 : parse_int(off_str, symbols);
            rs1 = parse_reg(rs1_str);
        } else {
            imm = parse_int(mem_op, symbols);
            rs1 = 0;
        }
        DecodedInstruction inst;
        inst.opcode = op;
        inst.is_imm = true;
        inst.rd = rd;
        inst.rs1 = rs1;
        inst.imm = imm;
        return encode_instruction(inst);
    }

    if (op == Opcode::MOV) {
        uint8_t rd = parse_reg(args[0]);
        std::string src_token = args[1];
        auto r_opt = parse_register_alias(src_token);
        DecodedInstruction inst;
        inst.opcode = op;
        inst.rd = rd;
        if (r_opt) {
            inst.is_imm = false;
            inst.rs1 = *r_opt;
            inst.rs2 = 0;
        } else {
            inst.is_imm = true;
            inst.rs1 = 0;
            inst.imm = parse_int(src_token, symbols);
        }
        return encode_instruction(inst);
    }

    if (op == Opcode::NOT) {
        DecodedInstruction inst;
        inst.opcode = op;
        inst.is_imm = false;
        inst.rd = parse_reg(args[0]);
        inst.rs1 = parse_reg(args[1]);
        inst.rs2 = 0;
        return encode_instruction(inst);
    }

    if (op == Opcode::CMP) {
        uint8_t rs1 = parse_reg(args[0]);
        std::string op2 = args[1];
        auto r_opt = parse_register_alias(op2);
        DecodedInstruction inst;
        inst.opcode = op;
        inst.rd = 0;
        inst.rs1 = rs1;
        if (r_opt) {
            inst.is_imm = false;
            inst.rs2 = *r_opt;
        } else {
            inst.is_imm = true;
            inst.imm = parse_int(op2, symbols);
        }
        return encode_instruction(inst);
    }

    // 3-operand ALU
    uint8_t rd = parse_reg(args[0]);
    uint8_t rs1 = parse_reg(args[1]);
    std::string op2 = args[2];
    auto r_opt = parse_register_alias(op2);
    DecodedInstruction inst;
    inst.opcode = op;
    inst.rd = rd;
    inst.rs1 = rs1;
    if (r_opt) {
        inst.is_imm = false;
        inst.rs2 = *r_opt;
    } else {
        inst.is_imm = true;
        inst.imm = parse_int(op2, symbols);
    }
    return encode_instruction(inst);
}

AssembledProgram Assembler::assemble(const std::string& source_text) {
    std::vector<std::string> raw_lines;
    std::stringstream ss(source_text);
    std::string line;
    while (std::getline(ss, line)) {
        raw_lines.push_back(line);
    }

    std::vector<std::string> expanded = preprocessor.expand_lines(raw_lines);
    AssembledProgram program;

    // Pass 1: Collect symbols
    std::string current_section = ".text";
    uint32_t text_pc = 0x00000000;
    uint32_t data_addr = 0x00001000;

    struct Pass1Item {
        std::string section;
        uint32_t addr;
        std::string line;
    };
    std::vector<Pass1Item> pass1_items;

    for (const auto& l : expanded) {
        size_t c1 = l.find(';');
        size_t c2 = l.find('#');
        size_t comm = std::min(c1 != std::string::npos ? c1 : l.size(),
                               c2 != std::string::npos ? c2 : l.size());
        std::string cleaned = trim(l.substr(0, comm));
        if (cleaned.empty()) continue;

        std::string lower = cleaned;
        std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
        if (lower.rfind(".text", 0) == 0) { current_section = ".text"; continue; }
        if (lower.rfind(".data", 0) == 0) { current_section = ".data"; continue; }
        if (lower.rfind(".globl", 0) == 0 || lower.rfind(".global", 0) == 0) continue;

        size_t colon = cleaned.find(':');
        if (colon != std::string::npos) {
            std::string label = trim(cleaned.substr(0, colon));
            if (!label.empty()) {
                program.symbol_table[label] = (current_section == ".text") ? text_pc : data_addr;
            }
            cleaned = trim(cleaned.substr(colon + 1));
        }

        if (cleaned.empty()) continue;

        if (current_section == ".text") {
            pass1_items.push_back({current_section, text_pc, cleaned});
            text_pc += 4;
        } else {
            pass1_items.push_back({current_section, data_addr, cleaned});
            data_addr += calc_data_size(cleaned);
        }
    }

    // Pass 2: Emit Machine Code
    for (const auto& item : pass1_items) {
        if (item.section == ".text") {
            uint32_t word = assemble_instruction(item.line, item.addr, program.symbol_table);
            program.text_words.push_back(static_cast<int32_t>(word));
            program.source_map[item.addr] = item.line;
            std::stringstream ss_list;
            ss_list << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << item.addr
                    << ": 0x" << std::setw(8) << word << " | " << item.line;
            program.listing.push_back(ss_list.str());
        } else {
            auto bytes_emitted = assemble_data(item.line, program.symbol_table);
            program.data_bytes.insert(program.data_bytes.end(), bytes_emitted.begin(), bytes_emitted.end());
        }
    }

    return program;
}

} // namespace risc201
