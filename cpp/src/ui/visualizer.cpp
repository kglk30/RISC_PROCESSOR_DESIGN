#include "ui/visualizer.hpp"
#include "core/stack.hpp"
#include <sstream>
#include <iomanip>
#include <vector>
#include <algorithm>

namespace risc201 {

std::string Visualizer::render_stack(const Memory& memory, const RegisterFile& rf, int max_words_above_fp) {
    uint32_t sp = static_cast<uint32_t>(rf.sp());
    uint32_t fp = static_cast<uint32_t>(rf.fp());
    uint32_t stack_base = memory.stack_base;

    std::stringstream ss;
    ss << "┌────────────────────────────────────────────────────────────────────────┐\n";
    ss << "│                     ACTIVE ASCII STACK FRAME MAP                       │\n";
    ss << "├────────────┬────────────┬─────────────┬────────────────────────────────┤\n";
    ss << "│  Address   │  Hex Word  │ Signed Dec  │ Frame Annotation / Symbols     │\n";
    ss << "├────────────┼────────────┼─────────────┼────────────────────────────────┤\n";

    uint32_t aligned_sp = (sp / 4) * 4;
    uint32_t display_top = std::min(stack_base, std::max(fp + static_cast<uint32_t>(max_words_above_fp * 4), aligned_sp + 32));
    uint32_t display_bottom = std::max(memory.stack_limit, aligned_sp > 4 ? aligned_sp - 4 : 0);

    for (int64_t addr = display_top; addr >= static_cast<int64_t>(display_bottom); addr -= 4) {
        uint32_t u_addr = static_cast<uint32_t>(addr);
        int32_t val = (u_addr + 3 < memory.size) ? memory.read_word(u_addr) : 0;
        uint32_t u32 = static_cast<uint32_t>(val);

        std::vector<std::string> annotations;
        bool is_sp = (u_addr == sp);
        bool is_fp = (u_addr == fp);

        if (is_sp && is_fp) {
            annotations.push_back("--> [SP & FP]");
        } else if (is_sp) {
            annotations.push_back("--> [SP] Top of Stack");
        } else if (is_fp) {
            annotations.push_back("--> [FP] Current Frame Base");
        }

        if (val == CANARY_MAGIC) {
            annotations.push_back("🛡️ Canary: 0x0001C0DE (Valid)");
        } else if (u_addr == fp - 4 && fp != sp) {
            std::stringstream ss_corrupt;
            ss_corrupt << "⚠️ Canary slot: 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << u32 << " (Corrupted!)";
            annotations.push_back(ss_corrupt.str());
        }

        if (u_addr == fp) {
            std::stringstream ss_save;
            ss_save << "Saved Old FP (points to 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << u32 << ")";
            annotations.push_back(ss_save.str());
        } else if (u_addr == fp + 4 && u_addr < stack_base) {
            std::stringstream ss_ra;
            ss_ra << "Saved RA (ret to 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << u32 << ")";
            annotations.push_back(ss_ra.str());
        } else if (u_addr > fp && u_addr < stack_base) {
            uint32_t arg_idx = (u_addr - fp - 4) / 4;
            annotations.push_back("Caller Slot / Arg #" + std::to_string(arg_idx));
        } else if (u_addr < fp && u_addr > sp) {
            uint32_t var_offset = fp - u_addr;
            annotations.push_back("Local Variable [FP - " + std::to_string(var_offset) + "]");
        }

        std::string annot_str;
        for (size_t i = 0; i < annotations.size(); ++i) {
            if (i > 0) annot_str += " | ";
            annot_str += annotations[i];
        }

        ss << "│ 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << u_addr << " │ "
           << "0x" << std::setw(8) << u32 << " │ "
           << std::dec << std::right << std::setw(11) << std::setfill(' ') << val << " │ "
           << std::left << std::setw(30) << annot_str << " │\n";
    }

    ss << "└────────────┴────────────┴─────────────┴────────────────────────────────┘\n";
    ss << " Stack Base: 0x" << std::hex << std::uppercase << stack_base
       << "  |  SP: 0x" << sp << "  |  FP: 0x" << fp << "  |  Limit: 0x" << memory.stack_limit << "\n";

    return ss.str();
}

std::string Visualizer::render_pipeline_4stage(const std::unordered_map<std::string, std::string>& stages, uint64_t cycle) {
    auto get_s = [&](const std::string& key) {
        auto it = stages.find(key);
        return it != stages.end() ? it->second : "NOP";
    };

    std::stringstream ss;
    ss << "┌─ 4-Stage Pipeline State (Cycle " << cycle << ") ──────────────────────────────────┐\n";
    ss << "│ [IF    ] : " << std::left << std::setw(58) << get_s("IF") << " │\n";
    ss << "│ [ID/OF ] : " << std::left << std::setw(58) << get_s("ID/OF") << " │\n";
    ss << "│ [EX/MEM] : " << std::left << std::setw(58) << get_s("EX/MEM") << " │\n";
    ss << "│ [WB    ] : " << std::left << std::setw(58) << get_s("WB") << " │\n";
    ss << "└────────────────────────────────────────────────────────────────────────┘\n";
    return ss.str();
}

std::string Visualizer::render_pipeline_6stage(const std::unordered_map<std::string, std::string>& stages, uint64_t cycle) {
    auto get_s = [&](const std::string& key) {
        auto it = stages.find(key);
        return it != stages.end() ? it->second : "NOP";
    };

    std::stringstream ss;
    ss << "┌─ 6-Stage Pipeline State (Cycle " << cycle << ") ──────────────────────────────────┐\n";
    ss << "│ [IF ] : " << std::left << std::setw(62) << get_s("IF") << " │\n";
    ss << "│ [ID ] : " << std::left << std::setw(62) << get_s("ID") << " │\n";
    ss << "│ [RR ] : " << std::left << std::setw(62) << get_s("RR") << " │\n";
    ss << "│ [EX ] : " << std::left << std::setw(62) << get_s("EX") << " │\n";
    ss << "│ [MEM] : " << std::left << std::setw(62) << get_s("MEM") << " │\n";
    ss << "│ [WB ] : " << std::left << std::setw(62) << get_s("WB") << " │\n";
    ss << "└────────────────────────────────────────────────────────────────────────┘\n";
    return ss.str();
}

} // namespace risc201
