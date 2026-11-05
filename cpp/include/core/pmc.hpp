#pragma once

#include <cstdint>
#include <string>
#include <unordered_map>

namespace risc201 {

class PMC {
public:
    uint64_t cycle_count{0};
    uint64_t instruction_count{0};
    uint64_t stall_count{0};
    uint64_t data_hazard_stalls{0};
    uint64_t load_use_stalls{0};
    uint64_t structural_stalls{0};
    uint64_t branch_count{0};
    uint64_t branch_mispredict_count{0};
    uint64_t forwarding_events{0};

    void reset();
    void tick_cycle() { cycle_count++; }
    void commit_instruction() { instruction_count++; }
    void record_stall(bool is_load_use = false, bool is_structural = false);
    void record_branch(bool mispredicted);
    void record_forwarding() { forwarding_events++; }

    double cpi() const;
    double ipc() const;
    double branch_mispredict_rate() const;

    std::string format_summary() const;
};

} // namespace risc201
