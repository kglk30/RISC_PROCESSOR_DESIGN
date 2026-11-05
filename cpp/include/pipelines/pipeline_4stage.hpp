#pragma once

#include <cstdint>
#include <optional>
#include <unordered_map>
#include "core/isa.hpp"
#include "core/registers.hpp"
#include "core/memory.hpp"
#include "core/pmc.hpp"
#include "alu/alu.hpp"
#include "pipelines/branch_predictor.hpp"
#include "pipelines/forwarding.hpp"

namespace risc201 {

struct Latch_IF_ID_4 {
    bool valid{false};
    uint32_t pc{0};
    uint32_t raw_word{0};
    bool pred_taken{false};
    uint32_t pred_target{0};
    void clear() { valid = false; pc = 0; raw_word = 0; pred_taken = false; pred_target = 0; }
};

struct Latch_ID_EX_4 {
    bool valid{false};
    uint32_t pc{0};
    std::optional<DecodedInstruction> inst{std::nullopt};
    int32_t valA{0};
    int32_t valB{0};
    bool pred_taken{false};
    uint32_t pred_target{0};
    void clear() { valid = false; pc = 0; inst = std::nullopt; valA = valB = 0; pred_taken = false; pred_target = 0; }
};

struct Latch_EX_WB_4 {
    bool valid{false};
    uint32_t pc{0};
    std::optional<DecodedInstruction> inst{std::nullopt};
    int32_t alu_result{0};
    int32_t mem_data{0};
    void clear() { valid = false; pc = 0; inst = std::nullopt; alu_result = mem_data = 0; }
};

class Processor4Stage {
public:
    Memory memory;
    RegisterFile rf;
    CSRFile csr;
    ALU alu;
    PMC pmc;
    BranchPredictor branch_predictor;
    HazardUnit hazard_unit;

    uint32_t pc{0};
    bool halted{false};
    bool exception_raised{false};
    std::optional<CPUException> last_exception{std::nullopt};

    Latch_IF_ID_4 if_id;
    Latch_ID_EX_4 id_ex;
    Latch_EX_WB_4 ex_wb;

    Processor4Stage(bool fwd = true, PredictorMode bm = PredictorMode::DYNAMIC_2BIT);
    void reset(uint32_t initial_pc = 0);
    bool step();
    bool run(uint64_t max_cycles = 1000000);

    std::unordered_map<std::string, std::string> get_stage_strings() const;

private:
    void _stage_wb();
    Latch_EX_WB_4 _stage_ex_mem();
    std::tuple<bool, bool, Latch_ID_EX_4> _stage_id_of(const Latch_EX_WB_4& next_ex_wb);
    Latch_IF_ID_4 _stage_if(bool flush = false);
};

} // namespace risc201
