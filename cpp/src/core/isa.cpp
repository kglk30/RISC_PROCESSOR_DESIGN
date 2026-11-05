#include "core/isa.hpp"
#include <algorithm>

namespace risc201 {

static const std::unordered_map<Opcode, std::string> OPCODE_NAMES = {
    {Opcode::ADD, "add"}, {Opcode::SUB, "sub"}, {Opcode::MUL, "mul"},
    {Opcode::DIV, "div"}, {Opcode::MOD, "mod"}, {Opcode::CMP, "cmp"},
    {Opcode::AND, "and"}, {Opcode::OR, "or"},   {Opcode::NOT, "not"},
    {Opcode::MOV, "mov"}, {Opcode::LSL, "lsl"}, {Opcode::LSR, "lsr"},
    {Opcode::ASR, "asr"}, {Opcode::NOP, "nop"}, {Opcode::LD, "ld"},
    {Opcode::ST, "st"},   {Opcode::BEQ, "beq"}, {Opcode::BGT, "bgt"},
    {Opcode::B, "b"},     {Opcode::CALL, "call"}, {Opcode::RET, "ret"},
    {Opcode::BLT, "blt"}, {Opcode::BNE, "bne"}, {Opcode::TRAP, "trap"},
    {Opcode::HLT, "hlt"}
};

static const std::unordered_map<std::string, Opcode> NAME_TO_OPCODE = {
    {"add", Opcode::ADD}, {"sub", Opcode::SUB}, {"mul", Opcode::MUL},
    {"div", Opcode::DIV}, {"mod", Opcode::MOD}, {"cmp", Opcode::CMP},
    {"and", Opcode::AND}, {"or", Opcode::OR},   {"not", Opcode::NOT},
    {"mov", Opcode::MOV}, {"lsl", Opcode::LSL}, {"lsr", Opcode::LSR},
    {"asr", Opcode::ASR}, {"nop", Opcode::NOP}, {"ld", Opcode::LD},
    {"st", Opcode::ST},   {"beq", Opcode::BEQ}, {"bgt", Opcode::BGT},
    {"b", Opcode::B},     {"call", Opcode::CALL}, {"ret", Opcode::RET},
    {"blt", Opcode::BLT}, {"bne", Opcode::BNE}, {"trap", Opcode::TRAP},
    {"hlt", Opcode::HLT}
};

std::string get_opcode_name(Opcode op) {
    auto it = OPCODE_NAMES.find(op);
    return it != OPCODE_NAMES.end() ? it->second : "unk";
}

std::optional<Opcode> parse_opcode(const std::string& name) {
    std::string lower = name;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    auto it = NAME_TO_OPCODE.find(lower);
    if (it != NAME_TO_OPCODE.end()) return it->second;
    return std::nullopt;
}

std::optional<uint8_t> parse_register_alias(const std::string& name) {
    std::string lower = name;
    std::transform(lower.begin(), lower.end(), lower.begin(), ::tolower);
    if (lower == "zero" || lower == "r0") return 0;
    if (lower == "fp" || lower == "r13") return 13;
    if (lower == "sp" || lower == "r14") return 14;
    if (lower == "ra" || lower == "lr" || lower == "r15") return 15;
    if (lower.size() >= 2 && lower[0] == 'r') {
        try {
            int idx = std::stoi(lower.substr(1));
            if (idx >= 0 && idx < 16) return static_cast<uint8_t>(idx);
        } catch (...) {}
    }
    return std::nullopt;
}

std::string get_register_name(uint8_t reg_idx) {
    if (reg_idx == 0) return "r0(zero)";
    if (reg_idx == 13) return "r13(fp)";
    if (reg_idx == 14) return "r14(sp)";
    if (reg_idx == 15) return "r15(ra)";
    return "r" + std::to_string(reg_idx);
}

int32_t sign_extend(uint32_t val, int bits) {
    val = val & ((1u << bits) - 1);
    if (val & (1u << (bits - 1))) {
        return static_cast<int32_t>(val - (1u << bits));
    }
    return static_cast<int32_t>(val);
}

bool is_branch_op(Opcode op) {
    return op == Opcode::BEQ || op == Opcode::BGT || op == Opcode::B ||
           op == Opcode::CALL || op == Opcode::RET || op == Opcode::BLT || op == Opcode::BNE;
}

bool is_memory_op(Opcode op) {
    return op == Opcode::LD || op == Opcode::ST;
}

bool is_alu_op(Opcode op) {
    return op == Opcode::ADD || op == Opcode::SUB || op == Opcode::MUL ||
           op == Opcode::DIV || op == Opcode::MOD || op == Opcode::CMP ||
           op == Opcode::AND || op == Opcode::OR  || op == Opcode::NOT ||
           op == Opcode::MOV || op == Opcode::LSL || op == Opcode::LSR || op == Opcode::ASR;
}

std::string DecodedInstruction::op_name() const {
    return get_opcode_name(opcode);
}

bool DecodedInstruction::writes_rf() const {
    if (opcode == Opcode::CMP || opcode == Opcode::ST  || opcode == Opcode::NOP ||
        opcode == Opcode::BEQ || opcode == Opcode::BGT || opcode == Opcode::B   ||
        opcode == Opcode::RET || opcode == Opcode::BLT || opcode == Opcode::BNE ||
        opcode == Opcode::TRAP || opcode == Opcode::HLT) {
        return false;
    }
    if (opcode == Opcode::CALL) return true;
    return true;
}

uint8_t DecodedInstruction::dest_reg() const {
    if (opcode == Opcode::CALL) return 15;
    return rd;
}

bool DecodedInstruction::reads_rs1() const {
    if (opcode == Opcode::NOP || opcode == Opcode::B || opcode == Opcode::CALL ||
        opcode == Opcode::RET || opcode == Opcode::TRAP || opcode == Opcode::HLT) {
        return false;
    }
    if (opcode == Opcode::MOV && is_imm) return false;
    return true;
}

bool DecodedInstruction::reads_rs2() const {
    if (is_imm) return false;
    if (opcode == Opcode::ST) return true;
    if (opcode == Opcode::NOT || opcode == Opcode::MOV || opcode == Opcode::NOP ||
        opcode == Opcode::LD  || opcode == Opcode::BEQ || opcode == Opcode::BGT ||
        opcode == Opcode::B   || opcode == Opcode::CALL || opcode == Opcode::RET ||
        opcode == Opcode::BLT || opcode == Opcode::BNE || opcode == Opcode::TRAP ||
        opcode == Opcode::HLT) {
        return false;
    }
    return true;
}

DecodedInstruction decode_instruction(uint32_t word) {
    DecodedInstruction inst;
    inst.raw = word;
    uint8_t op_val = static_cast<uint8_t>((word >> 27) & 0x1F);
    inst.opcode = static_cast<Opcode>(op_val);

    if (inst.opcode == Opcode::TRAP) {
        inst.trap_id = word & 0x07FFFFFF;
        return inst;
    }

    if (inst.opcode == Opcode::HLT || inst.opcode == Opcode::NOP || inst.opcode == Opcode::RET) {
        return inst;
    }

    if (is_branch_op(inst.opcode)) {
        inst.offset = sign_extend(word & 0x07FFFFFF, 27);
        return inst;
    }

    inst.is_imm = bool((word >> 26) & 0x01);
    inst.rd = static_cast<uint8_t>((word >> 22) & 0x0F);
    inst.rs1 = static_cast<uint8_t>((word >> 18) & 0x0F);

    if (inst.is_imm) {
        inst.imm = sign_extend(word & 0x3FFFF, 18);
    } else {
        inst.rs2 = static_cast<uint8_t>((word >> 14) & 0x0F);
    }

    return inst;
}

uint32_t encode_instruction(const DecodedInstruction& inst) {
    uint32_t op = static_cast<uint32_t>(inst.opcode) & 0x1F;

    if (inst.opcode == Opcode::TRAP) {
        return (op << 27) | (inst.trap_id & 0x07FFFFFF);
    }

    if (inst.opcode == Opcode::NOP || inst.opcode == Opcode::HLT || inst.opcode == Opcode::RET) {
        return (op << 27);
    }

    if (is_branch_op(inst.opcode)) {
        return (op << 27) | (static_cast<uint32_t>(inst.offset) & 0x07FFFFFF);
    }

    uint32_t is_imm_bit = inst.is_imm ? 1 : 0;
    uint32_t rd = inst.rd & 0x0F;
    uint32_t rs1 = inst.rs1 & 0x0F;

    if (inst.is_imm) {
        uint32_t imm = static_cast<uint32_t>(inst.imm) & 0x3FFFF;
        return (op << 27) | (is_imm_bit << 26) | (rd << 22) | (rs1 << 18) | imm;
    } else {
        uint32_t rs2 = inst.rs2 & 0x0F;
        return (op << 27) | (is_imm_bit << 26) | (rd << 22) | (rs1 << 18) | (rs2 << 14);
    }
}

} // namespace risc201
