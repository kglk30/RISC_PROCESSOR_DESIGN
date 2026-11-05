#include "alu/alu.hpp"
#include <cmath>
#include <cstdlib>

namespace risc201 {

std::string ALUFlags::to_string() const {
    return "[Z=" + std::to_string(Z) + " N=" + std::to_string(N) +
           " C=" + std::to_string(C) + " V=" + std::to_string(V) + "]";
}

ALU::ALU(MultiplierAlgorithm ma, DividerAlgorithm da) : mul_algo(ma), div_algo(da) {}

std::pair<int32_t, int> ALU::booth_multiply(int32_t multiplicand, int32_t multiplier) {
    int32_t M = multiplicand;
    uint32_t Q = static_cast<uint32_t>(multiplier);
    uint32_t A = 0;
    uint32_t Q_minus_1 = 0;
    int cycles = 32;

    for (int i = 0; i < 32; ++i) {
        uint32_t q0 = Q & 1;
        if (q0 == 1 && Q_minus_1 == 0) {
            A = A - static_cast<uint32_t>(M);
        } else if (q0 == 0 && Q_minus_1 == 1) {
            A = A + static_cast<uint32_t>(M);
        }

        uint32_t sign_A = (A & 0x80000000);
        Q_minus_1 = Q & 1;
        Q = ((A & 1) << 31) | (Q >> 1);
        A = (A >> 1) | sign_A;
    }

    return {static_cast<int32_t>(Q), cycles};
}

std::pair<int32_t, int> ALU::shift_add_multiply(int32_t a, int32_t b) {
    uint32_t u_a = static_cast<uint32_t>(a);
    uint32_t u_b = static_cast<uint32_t>(b);
    uint32_t product = 0;
    int cycles = 32;

    for (int i = 0; i < 32; ++i) {
        if ((u_b >> i) & 1) {
            product += (u_a << i);
        }
    }
    return {static_cast<int32_t>(product), cycles};
}

std::tuple<int32_t, int32_t, int> ALU::restoring_divide(int32_t dividend, int32_t divisor) {
    if (divisor == 0) {
        throw DivisionByZeroException();
    }

    int sign = ((dividend < 0) ^ (divisor < 0)) ? -1 : 1;
    uint64_t u_dividend = static_cast<uint64_t>(std::abs(static_cast<int64_t>(dividend)));
    uint64_t u_divisor = static_cast<uint64_t>(std::abs(static_cast<int64_t>(divisor)));

    uint64_t A = 0;
    uint64_t Q = u_dividend;
    uint64_t M = u_divisor;
    int n = 32;

    for (int i = 0; i < n; ++i) {
        A = ((A << 1) | ((Q >> 31) & 1)) & 0xFFFFFFFF;
        Q = (Q << 1) & 0xFFFFFFFF;

        int64_t trial = static_cast<int64_t>(A) - static_cast<int64_t>(M);
        if (trial < 0) {
            // Restore A
        } else {
            A = static_cast<uint64_t>(trial);
            Q |= 1;
        }
    }

    int32_t quotient = static_cast<int32_t>(sign * static_cast<int64_t>(Q));
    int32_t remainder = static_cast<int32_t>(dividend >= 0 ? A : -static_cast<int64_t>(A));
    return {quotient, remainder, n};
}

int32_t ALU::execute(Opcode op, int32_t opA, int32_t opB, bool update_flags) {
    int32_t result = 0;

    switch (op) {
        case Opcode::ADD: {
            uint32_t uA = static_cast<uint32_t>(opA);
            uint32_t uB = static_cast<uint32_t>(opB);
            uint64_t uRes = static_cast<uint64_t>(uA) + static_cast<uint64_t>(uB);
            result = static_cast<int32_t>(uRes & 0xFFFFFFFF);
            if (update_flags) {
                flags.C = (uRes > 0xFFFFFFFF);
                flags.V = ((not ((opA ^ opB) & 0x80000000)) && ((opA ^ result) & 0x80000000));
            }
            break;
        }

        case Opcode::SUB:
        case Opcode::CMP: {
            uint32_t uA = static_cast<uint32_t>(opA);
            uint32_t uB = static_cast<uint32_t>(opB);
            uint32_t uRes = uA - uB;
            result = static_cast<int32_t>(uRes);
            if (update_flags) {
                flags.C = (uA >= uB);
                flags.V = (((opA ^ opB) & 0x80000000) && ((opA ^ result) & 0x80000000));
            }
            break;
        }

        case Opcode::MUL: {
            if (mul_algo == MultiplierAlgorithm::BOOTH) {
                result = booth_multiply(opA, opB).first;
            } else if (mul_algo == MultiplierAlgorithm::SHIFT_AND_ADD) {
                result = shift_add_multiply(opA, opB).first;
            } else {
                result = static_cast<int32_t>(static_cast<uint32_t>(opA) * static_cast<uint32_t>(opB));
            }
            if (update_flags) {
                int64_t full = static_cast<int64_t>(opA) * static_cast<int64_t>(opB);
                flags.V = (full < -0x80000000LL || full > 0x7FFFFFFFLL);
            }
            break;
        }

        case Opcode::DIV: {
            if (opB == 0) throw DivisionByZeroException();
            if (div_algo == DividerAlgorithm::RESTORING) {
                result = std::get<0>(restoring_divide(opA, opB));
            } else {
                result = opA / opB;
            }
            break;
        }

        case Opcode::MOD: {
            if (opB == 0) throw DivisionByZeroException();
            if (div_algo == DividerAlgorithm::RESTORING) {
                result = std::get<1>(restoring_divide(opA, opB));
            } else {
                result = opA % opB;
            }
            break;
        }

        case Opcode::AND:
            result = opA & opB;
            break;

        case Opcode::OR:
            result = opA | opB;
            break;

        case Opcode::NOT:
            result = ~opA;
            break;

        case Opcode::MOV:
            result = opB;
            break;

        case Opcode::LSL: {
            uint32_t shift = static_cast<uint32_t>(opB) & 0x1F;
            result = static_cast<int32_t>(static_cast<uint32_t>(opA) << shift);
            break;
        }

        case Opcode::LSR: {
            uint32_t shift = static_cast<uint32_t>(opB) & 0x1F;
            result = static_cast<int32_t>(static_cast<uint32_t>(opA) >> shift);
            break;
        }

        case Opcode::ASR: {
            uint32_t shift = static_cast<uint32_t>(opB) & 0x1F;
            result = opA >> shift;
            break;
        }

        default:
            result = opB;
            break;
    }

    if (update_flags) {
        flags.Z = (result == 0);
        flags.N = (result < 0);
    }

    return result;
}

} // namespace risc201
