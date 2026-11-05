#pragma once

#include <cstdint>
#include <string>
#include <vector>
#include <array>
#include <exception>
#include <optional>
#include <unordered_map>

namespace risc201 {

enum class CSRCause : uint32_t {
    NONE                    = 0x00,
    DIVISION_BY_ZERO        = 0x01,
    ILLEGAL_INSTRUCTION     = 0x02,
    MISALIGNED_ACCESS       = 0x03,
    STACK_OVERFLOW          = 0x04,
    STACK_UNDERFLOW         = 0x05,
    STACK_CANARY_CORRUPTED  = 0x06,
    OUT_OF_BOUNDS           = 0x07,
    BREAKPOINT              = 0x08,
    TRAP_CALL               = 0x09
};

std::string get_cause_name(CSRCause cause);

class CPUException : public std::exception {
public:
    CSRCause cause;
    uint32_t pc;
    std::string message;
    uint32_t badvaddr;

    CPUException(CSRCause c, uint32_t p, const std::string& msg, std::optional<uint32_t> bad = std::nullopt);
    const char* what() const noexcept override;
};

class CSRFile {
public:
    uint32_t epc{0};
    CSRCause cause{CSRCause::NONE};
    uint32_t status{0x01}; // IE=1 by default
    uint32_t badvaddr{0};

    void trigger_exception(CSRCause c, uint32_t faulting_pc, std::optional<uint32_t> bad = std::nullopt);
    void clear_exception();
    std::unordered_map<std::string, std::string> to_dict() const;
};

class RegisterFile {
public:
    static constexpr size_t NUM_REGS = 16;
    std::array<int32_t, NUM_REGS> regs{};
    uint16_t modified_mask{0};
    std::optional<uint8_t> last_written_reg{std::nullopt};

    RegisterFile();
    void reset(uint32_t initial_sp = 0x00004000);

    // Hardwired r0: read(0) -> 0; write(0, val) -> discarded
    int32_t read(uint8_t reg_idx) const;
    void write(uint8_t reg_idx, int32_t value);

    void clear_modified_flags();

    int32_t sp() const { return read(14); }
    void set_sp(int32_t val) { write(14, val); }

    int32_t fp() const { return read(13); }
    void set_fp(int32_t val) { write(13, val); }

    int32_t ra() const { return read(15); }
    void set_ra(int32_t val) { write(15, val); }
};

} // namespace risc201
