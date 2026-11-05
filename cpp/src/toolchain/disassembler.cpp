#include "toolchain/disassembler.hpp"
#include "core/isa.hpp"
#include <sstream>
#include <iomanip>

namespace risc201 {

std::string Disassembler::reg_name(uint8_t reg_idx) {
    if (reg_idx == 0) return "r0";
    if (reg_idx == 13) return "fp";
    if (reg_idx == 14) return "sp";
    if (reg_idx == 15) return "ra";
    return "r" + std::to_string(reg_idx);
}

std::string Disassembler::disassemble_word(uint32_t word, uint32_t current_pc) {
    DecodedInstruction inst = decode_instruction(word);
    Opcode op = inst.opcode;

    if (op == Opcode::NOP) return "nop";
    if (op == Opcode::HLT) return "hlt";
    if (op == Opcode::RET) return "ret";
    if (op == Opcode::TRAP) return "trap " + std::to_string(inst.trap_id);

    if (is_branch_op(op)) {
        uint32_t target_pc = current_pc + static_cast<uint32_t>(inst.offset * 4);
        std::stringstream ss;
        ss << inst.op_name() << " 0x" << std::hex << std::uppercase << std::setw(4) << std::setfill('0')
           << target_pc << "  ; offset=" << std::dec << inst.offset;
        return ss.str();
    }

    if (is_memory_op(op)) {
        return inst.op_name() + " " + reg_name(inst.rd) + ", " + std::to_string(inst.imm) + "[" + reg_name(inst.rs1) + "]";
    }

    if (op == Opcode::MOV) {
        if (inst.is_imm) {
            return "mov " + reg_name(inst.rd) + ", " + std::to_string(inst.imm);
        } else {
            return "mov " + reg_name(inst.rd) + ", " + reg_name(inst.rs1);
        }
    }

    if (op == Opcode::NOT) {
        return "not " + reg_name(inst.rd) + ", " + reg_name(inst.rs1);
    }

    if (op == Opcode::CMP) {
        if (inst.is_imm) {
            return "cmp " + reg_name(inst.rs1) + ", " + std::to_string(inst.imm);
        } else {
            return "cmp " + reg_name(inst.rs1) + ", " + reg_name(inst.rs2);
        }
    }

    // Standard 3-operand ALU
    if (inst.is_imm) {
        return inst.op_name() + " " + reg_name(inst.rd) + ", " + reg_name(inst.rs1) + ", " + std::to_string(inst.imm);
    } else {
        return inst.op_name() + " " + reg_name(inst.rd) + ", " + reg_name(inst.rs1) + ", " + reg_name(inst.rs2);
    }
}

std::string Disassembler::disassemble_hex(const std::string& hex_str, uint32_t current_pc) {
    uint32_t word = std::stoul(hex_str, nullptr, 16);
    return disassemble_word(word, current_pc);
}

std::vector<std::string> Disassembler::disassemble_words(const std::vector<int32_t>& words, uint32_t start_pc) {
    std::vector<std::string> out;
    for (size_t i = 0; i < words.size(); ++i) {
        uint32_t pc = start_pc + static_cast<uint32_t>(i * 4);
        uint32_t u32 = static_cast<uint32_t>(words[i]);
        std::stringstream ss;
        ss << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << pc
           << ": 0x" << std::setw(8) << u32 << "    " << disassemble_word(u32, pc);
        out.push_back(ss.str());
    }
    return out;
}

} // namespace risc201
