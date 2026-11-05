#include "core/registers.hpp"
#include <sstream>
#include <iomanip>

namespace risc201 {

std::string get_cause_name(CSRCause cause) {
    switch (cause) {
        case CSRCause::NONE: return "None";
        case CSRCause::DIVISION_BY_ZERO: return "Division By Zero";
        case CSRCause::ILLEGAL_INSTRUCTION: return "Illegal Instruction";
        case CSRCause::MISALIGNED_ACCESS: return "Misaligned Memory Access";
        case CSRCause::STACK_OVERFLOW: return "Stack Overflow Exception";
        case CSRCause::STACK_UNDERFLOW: return "Stack Underflow Exception";
        case CSRCause::STACK_CANARY_CORRUPTED: return "Security Trap: Stack Canary Corrupted!";
        case CSRCause::OUT_OF_BOUNDS: return "Out of Bounds Memory Reference";
        case CSRCause::BREAKPOINT: return "Breakpoint Trap";
        case CSRCause::TRAP_CALL: return "Software Trap";
        default: return "Unknown Exception";
    }
}

CPUException::CPUException(CSRCause c, uint32_t p, const std::string& msg, std::optional<uint32_t> bad)
    : cause(c), pc(p), message(msg), badvaddr(bad.value_or(p)) {}

const char* CPUException::what() const noexcept {
    return message.c_str();
}

void CSRFile::trigger_exception(CSRCause c, uint32_t faulting_pc, std::optional<uint32_t> bad) {
    epc = faulting_pc;
    cause = c;
    status |= 0x04; // Set EX bit (bit 2)
    badvaddr = bad.value_or(faulting_pc);
}

void CSRFile::clear_exception() {
    cause = CSRCause::NONE;
    status &= ~0x04; // Clear EX bit
}

std::unordered_map<std::string, std::string> CSRFile::to_dict() const {
    std::stringstream ss_epc, ss_bad, ss_stat;
    ss_epc << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << epc;
    ss_bad << "0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << badvaddr;
    ss_stat << "0x" << std::hex << std::uppercase << std::setw(2) << std::setfill('0') << status
            << " (EX=" << ((status & 4) ? 1 : 0) << " Mode=" << ((status & 2) ? "Kernel" : "User")
            << " IE=" << ((status & 1) ? 1 : 0) << ")";

    return {
        {"EPC", ss_epc.str()},
        {"CAUSE", std::to_string(static_cast<uint32_t>(cause)) + " (" + get_cause_name(cause) + ")"},
        {"STATUS", ss_stat.str()},
        {"BADVADDR", ss_bad.str()}
    };
}

RegisterFile::RegisterFile() {
    reset();
}

void RegisterFile::reset(uint32_t initial_sp) {
    regs.fill(0);
    regs[14] = static_cast<int32_t>(initial_sp); // sp
    regs[13] = static_cast<int32_t>(initial_sp); // fp
    modified_mask = 0;
    last_written_reg = std::nullopt;
}

int32_t RegisterFile::read(uint8_t reg_idx) const {
    // Hardwired r0: ALWAYS returns 0
    if (reg_idx == 0) return 0;
    if (reg_idx < NUM_REGS) return regs[reg_idx];
    return 0;
}

void RegisterFile::write(uint8_t reg_idx, int32_t value) {
    // Hardwired r0: Discard write attempt
    if (reg_idx == 0) return;
    if (reg_idx < NUM_REGS) {
        regs[reg_idx] = value;
        last_written_reg = reg_idx;
        modified_mask |= (1 << reg_idx);
    }
}

void RegisterFile::clear_modified_flags() {
    modified_mask = 0;
    last_written_reg = std::nullopt;
}

} // namespace risc201
