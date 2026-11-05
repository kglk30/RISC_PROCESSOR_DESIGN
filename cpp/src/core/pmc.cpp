#include "core/pmc.hpp"
#include <sstream>
#include <iomanip>

namespace risc201 {

void PMC::reset() {
    cycle_count = 0;
    instruction_count = 0;
    stall_count = 0;
    data_hazard_stalls = 0;
    load_use_stalls = 0;
    structural_stalls = 0;
    branch_count = 0;
    branch_mispredict_count = 0;
    forwarding_events = 0;
}

void PMC::record_stall(bool is_load_use, bool is_structural) {
    stall_count++;
    if (is_load_use) {
        load_use_stalls++;
        data_hazard_stalls++;
    } else if (is_structural) {
        structural_stalls++;
    } else {
        data_hazard_stalls++;
    }
}

void PMC::record_branch(bool mispredicted) {
    branch_count++;
    if (mispredicted) {
        branch_mispredict_count++;
    }
}

double PMC::cpi() const {
    if (instruction_count == 0) return 0.0;
    return static_cast<double>(cycle_count) / static_cast<double>(instruction_count);
}

double PMC::ipc() const {
    if (cycle_count == 0) return 0.0;
    return static_cast<double>(instruction_count) / static_cast<double>(cycle_count);
}

double PMC::branch_mispredict_rate() const {
    if (branch_count == 0) return 0.0;
    return (static_cast<double>(branch_mispredict_count) / static_cast<double>(branch_count)) * 100.0;
}

std::string PMC::format_summary() const {
    std::stringstream ss;
    ss << "╔══════════════════════════════════════════════════════════════╗\n";
    ss << "║        HARDWARE PERFORMANCE MONITORING COUNTERS (PMC)        ║\n";
    ss << "╠══════════════════════════════════════════════════════════════╣\n";

    auto row = [&](const std::string& label, const std::string& val) {
        ss << "║  " << std::left << std::setw(28) << label << ": "
           << std::right << std::setw(26) << val << "  ║\n";
    };

    row("Cycles", std::to_string(cycle_count));
    row("Instructions Committed", std::to_string(instruction_count));
    row("Total Stalls", std::to_string(stall_count));
    row("Data Hazard Stalls", std::to_string(data_hazard_stalls));
    row("Load-Use Stalls", std::to_string(load_use_stalls));
    row("Structural Stalls", std::to_string(structural_stalls));
    row("Branches Evaluated", std::to_string(branch_count));
    row("Branch Mispredicts", std::to_string(branch_mispredict_count));

    std::stringstream ss_rate, ss_cpi, ss_ipc;
    ss_rate << std::fixed << std::setprecision(2) << branch_mispredict_rate() << "%";
    ss_cpi << std::fixed << std::setprecision(3) << cpi();
    ss_ipc << std::fixed << std::setprecision(3) << ipc();

    row("Mispredict Rate (%)", ss_rate.str());
    row("Forwarding Events", std::to_string(forwarding_events));
    row("CPI", ss_cpi.str());
    row("IPC", ss_ipc.str());

    ss << "╚══════════════════════════════════════════════════════════════╝\n";
    return ss.str();
}

} // namespace risc201
