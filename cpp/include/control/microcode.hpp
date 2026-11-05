#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>
#include <optional>
#include "core/isa.hpp"
#include "core/registers.hpp"
#include "core/memory.hpp"
#include "core/pmc.hpp"
#include "alu/alu.hpp"

namespace risc201 {

enum class MicroSeqOp : uint8_t {
    NEXT        = 0,
    DISPATCH    = 1,
    FETCH       = 2,
    JUMP        = 3,
    BRANCH_COND = 4
};

struct HorizontalMicrocode {
    bool pc_write{false};
    uint8_t pc_src{0};
    bool mem_read{false};
    bool mem_write{false};
    bool mem_to_reg{false};
    bool ir_write{false};
    bool reg_write{false};
    uint8_t alu_srcA{0};
    uint8_t alu_srcB{0};
    Opcode alu_op{Opcode::NOP};
    MicroSeqOp seq_op{MicroSeqOp::NEXT};
    uint8_t next_uaddr{0};
    std::string name;
};

struct VerticalMicrocode {
    Opcode alu_func{Opcode::NOP};
    uint8_t src_sel{0};
    uint8_t dst_sel{0};
    uint8_t mem_ctrl{0};
    bool reg_write{false};
    MicroSeqOp seq_ctrl{MicroSeqOp::NEXT};
    uint8_t next_uaddr{0};
    std::string name;
};

class ControlStore {
public:
    std::unordered_map<uint8_t, HorizontalMicrocode> horizontal_rom;
    std::unordered_map<uint8_t, VerticalMicrocode> vertical_rom;
    std::unordered_map<Opcode, uint8_t> dispatch_table;

    ControlStore();
private:
    void build_microcode();
};

class MicroprogrammedCPU {
public:
    Memory memory;
    RegisterFile rf;
    CSRFile csr;
    ALU alu;
    PMC pmc;
    ControlStore store;
    bool use_vertical{false};

    uint32_t pc{0};
    uint32_t ir{0};
    uint32_t mar{0};
    uint32_t mdr{0};
    std::optional<DecodedInstruction> current_inst{std::nullopt};

    uint8_t upc{0};
    bool halted{false};
    uint64_t total_micro_cycles{0};

    explicit MicroprogrammedCPU(bool vertical = false);
    void reset(uint32_t initial_pc = 0);
    bool step_micro();
    bool step_macro();
    bool run(uint64_t max_micro_cycles = 1000000);
};

} // namespace risc201
