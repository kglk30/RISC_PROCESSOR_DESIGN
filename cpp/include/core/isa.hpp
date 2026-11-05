#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <optional>

namespace risc201 {

enum class Opcode : uint8_t {
    ADD  = 0,
    SUB  = 1,
    MUL  = 2,
    DIV  = 3,
    MOD  = 4,
    CMP  = 5,
    AND  = 6,
    OR   = 7,
    NOT  = 8,
    MOV  = 9,
    LSL  = 10,
    LSR  = 11,
    ASR  = 12,
    NOP  = 13,
    LD   = 14,
    ST   = 15,
    BEQ  = 16,
    BGT  = 17,
    B    = 18,
    CALL = 19,
    RET  = 20,
    BLT  = 21,
    BNE  = 22,
    TRAP = 23,
    HLT  = 31
};

struct DecodedInstruction {
    uint32_t raw{0};
    Opcode opcode{Opcode::NOP};
    bool is_imm{false};
    uint8_t rd{0};
    uint8_t rs1{0};
    uint8_t rs2{0};
    int32_t imm{0};
    int32_t offset{0};
    uint32_t trap_id{0};

    std::string op_name() const;
    bool writes_rf() const;
    uint8_t dest_reg() const;
    bool reads_rs1() const;
    bool reads_rs2() const;
};

int32_t sign_extend(uint32_t val, int bits);
inline uint32_t to_unsigned32(int32_t val) { return static_cast<uint32_t>(val); }
inline int32_t to_signed32(uint32_t val) { return static_cast<int32_t>(val); }

bool is_branch_op(Opcode op);
bool is_memory_op(Opcode op);
bool is_alu_op(Opcode op);

DecodedInstruction decode_instruction(uint32_t word);
uint32_t encode_instruction(const DecodedInstruction& inst);

std::optional<uint8_t> parse_register_alias(const std::string& name);
std::string get_register_name(uint8_t reg_idx);
std::string get_opcode_name(Opcode op);
std::optional<Opcode> parse_opcode(const std::string& name);

} // namespace risc201
