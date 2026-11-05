#pragma once

#include <cstdint>
#include <string>
#include <tuple>
#include <exception>
#include "core/isa.hpp"

namespace risc201 {

enum class MultiplierAlgorithm {
    FAST,
    BOOTH,
    SHIFT_AND_ADD
};

enum class DividerAlgorithm {
    FAST,
    RESTORING,
    NON_RESTORING
};

struct ALUFlags {
    bool Z{false}; // Zero flag
    bool N{false}; // Negative flag
    bool C{false}; // Carry / Borrow flag
    bool V{false}; // Overflow flag

    void reset() { Z = N = C = V = false; }
    std::string to_string() const;
};

class DivisionByZeroException : public std::exception {
public:
    const char* what() const noexcept override {
        return "ALU Division by zero";
    }
};

class ALU {
public:
    ALUFlags flags;
    MultiplierAlgorithm mul_algo{MultiplierAlgorithm::FAST};
    DividerAlgorithm div_algo{DividerAlgorithm::FAST};

    ALU(MultiplierAlgorithm ma = MultiplierAlgorithm::FAST, DividerAlgorithm da = DividerAlgorithm::FAST);

    int32_t execute(Opcode op, int32_t opA, int32_t opB, bool update_flags = true);

    static std::pair<int32_t, int> booth_multiply(int32_t multiplicand, int32_t multiplier);
    static std::pair<int32_t, int> shift_add_multiply(int32_t a, int32_t b);
    static std::tuple<int32_t, int32_t, int> restoring_divide(int32_t dividend, int32_t divisor);
};

} // namespace risc201
