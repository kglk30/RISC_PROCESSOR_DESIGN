#include "core/memory.hpp"
#include <sstream>
#include <iomanip>

namespace risc201 {

Memory::Memory(size_t sz, uint32_t sb, uint32_t sl, uint32_t rb, uint32_t rl)
    : size(sz), stack_base(sb), stack_limit(sl), redzone_base(rb), redzone_limit(rl), bytes(sz, 0) {}

void Memory::reset() {
    std::fill(bytes.begin(), bytes.end(), 0);
    last_written_addr = std::nullopt;
    write_history.clear();
}

void Memory::check_alignment(uint32_t addr, uint32_t pc) const {
    if (addr % 4 != 0) {
        std::stringstream ss;
        ss << "Misaligned 32-bit word access at address 0x" << std::hex << std::uppercase
           << std::setw(8) << std::setfill('0') << addr << " (must be 4-byte aligned)";
        throw CPUException(CSRCause::MISALIGNED_ACCESS, pc, ss.str(), addr);
    }
}

void Memory::check_bounds(uint32_t addr, uint32_t pc) const {
    if (addr + 3 >= size) {
        std::stringstream ss;
        ss << "Memory access out of bounds: 0x" << std::hex << std::uppercase
           << std::setw(8) << std::setfill('0') << addr;
        throw CPUException(CSRCause::OUT_OF_BOUNDS, pc, ss.str(), addr);
    }
}

void Memory::check_stack_safety(uint32_t current_sp, uint32_t pc) const {
    if (current_sp > stack_base) {
        std::stringstream ss;
        ss << "Stack underflow detected: SP=0x" << std::hex << std::uppercase << current_sp
           << " exceeds stack base 0x" << stack_base;
        throw CPUException(CSRCause::STACK_UNDERFLOW, pc, ss.str(), current_sp);
    }
    if (current_sp < stack_limit) {
        std::stringstream ss;
        ss << "Stack overflow detected: SP=0x" << std::hex << std::uppercase << current_sp
           << " penetrated below stack limit 0x" << stack_limit;
        throw CPUException(CSRCause::STACK_OVERFLOW, pc, ss.str(), current_sp);
    }
}

int32_t Memory::read_word(uint32_t addr, uint32_t pc) const {
    check_bounds(addr, pc);
    check_alignment(addr, pc);

    uint32_t b0 = bytes[addr];
    uint32_t b1 = bytes[addr + 1];
    uint32_t b2 = bytes[addr + 2];
    uint32_t b3 = bytes[addr + 3];
    uint32_t u32 = b0 | (b1 << 8) | (b2 << 16) | (b3 << 24);
    return static_cast<int32_t>(u32);
}

void Memory::write_word(uint32_t addr, int32_t value, uint32_t pc) {
    check_bounds(addr, pc);
    check_alignment(addr, pc);

    if (addr >= redzone_base && addr < redzone_limit) {
        std::stringstream ss;
        ss << "Security violation: Attempted write into Stack Red Zone / Guard Page at 0x"
           << std::hex << std::uppercase << addr;
        throw CPUException(CSRCause::STACK_OVERFLOW, pc, ss.str(), addr);
    }

    uint32_t u32 = static_cast<uint32_t>(value);
    bytes[addr]     = static_cast<uint8_t>(u32 & 0xFF);
    bytes[addr + 1] = static_cast<uint8_t>((u32 >> 8) & 0xFF);
    bytes[addr + 2] = static_cast<uint8_t>((u32 >> 16) & 0xFF);
    bytes[addr + 3] = static_cast<uint8_t>((u32 >> 24) & 0xFF);

    last_written_addr = addr;
    write_history[addr] = value;
}

void Memory::load_words(uint32_t start_addr, const std::vector<int32_t>& words) {
    for (size_t i = 0; i < words.size(); ++i) {
        write_word(start_addr + static_cast<uint32_t>(i * 4), words[i], 0);
    }
}

void Memory::load_bytes(uint32_t start_addr, const std::vector<uint8_t>& raw_data) {
    check_bounds(start_addr);
    check_bounds(start_addr + static_cast<uint32_t>(raw_data.size()) - 1);
    std::copy(raw_data.begin(), raw_data.end(), bytes.begin() + start_addr);
}

} // namespace risc201
