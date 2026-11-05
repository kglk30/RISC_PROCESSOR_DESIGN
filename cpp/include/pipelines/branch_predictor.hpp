#pragma once

#include <cstdint>
#include <unordered_map>
#include <utility>
#include "core/isa.hpp"

namespace risc201 {

enum class PredictorMode {
    STATIC_NOT_TAKEN,
    STATIC_TAKEN,
    DYNAMIC_2BIT
};

class BranchPredictor {
public:
    PredictorMode mode{PredictorMode::DYNAMIC_2BIT};
    size_t btb_size{64};
    std::unordered_map<uint32_t, uint32_t> btb;
    std::unordered_map<uint32_t, uint8_t> counters; // 0..3 (Default: 1 = WNT)

    explicit BranchPredictor(PredictorMode m = PredictorMode::DYNAMIC_2BIT, size_t sz = 64);
    void reset();

    uint8_t get_counter_state(uint32_t pc) const;
    std::pair<bool, uint32_t> predict(uint32_t pc, Opcode op, uint32_t default_next_pc);
    void update(uint32_t pc, Opcode op, bool actual_taken, uint32_t actual_target);
};

} // namespace risc201
