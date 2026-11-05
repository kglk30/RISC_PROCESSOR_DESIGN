#include "pipelines/branch_predictor.hpp"
#include <algorithm>

namespace risc201 {

BranchPredictor::BranchPredictor(PredictorMode m, size_t sz) : mode(m), btb_size(sz) {}

void BranchPredictor::reset() {
    btb.clear();
    counters.clear();
}

uint8_t BranchPredictor::get_counter_state(uint32_t pc) const {
    auto it = counters.find(pc);
    return it != counters.end() ? it->second : 1; // Default: Weakly Not-Taken (1)
}

std::pair<bool, uint32_t> BranchPredictor::predict(uint32_t pc, Opcode op, uint32_t default_next_pc) {
    if (op == Opcode::B || op == Opcode::CALL) {
        auto it = btb.find(pc);
        uint32_t target = it != btb.end() ? it->second : default_next_pc;
        return {true, target};
    }

    if (op == Opcode::RET) {
        auto it = btb.find(pc);
        uint32_t target = it != btb.end() ? it->second : default_next_pc;
        return {true, target};
    }

    if (!is_branch_op(op)) {
        return {false, default_next_pc};
    }

    if (mode == PredictorMode::STATIC_NOT_TAKEN) {
        return {false, default_next_pc};
    } else if (mode == PredictorMode::STATIC_TAKEN) {
        auto it = btb.find(pc);
        uint32_t target = it != btb.end() ? it->second : default_next_pc;
        return {true, target};
    } else { // DYNAMIC_2BIT
        uint8_t state = get_counter_state(pc);
        bool predict_taken = (state >= 2);
        auto it = btb.find(pc);
        if (predict_taken && it != btb.end()) {
            return {true, it->second};
        }
        return {false, default_next_pc};
    }
}

void BranchPredictor::update(uint32_t pc, Opcode op, bool actual_taken, uint32_t actual_target) {
    if (!is_branch_op(op)) return;

    if (actual_taken) {
        btb[pc] = actual_target;
    }

    if (mode == PredictorMode::DYNAMIC_2BIT) {
        uint8_t state = get_counter_state(pc);
        if (actual_taken) {
            counters[pc] = std::min<uint8_t>(3, state + 1);
        } else {
            counters[pc] = state > 0 ? state - 1 : 0;
        }
    }
}

} // namespace risc201
