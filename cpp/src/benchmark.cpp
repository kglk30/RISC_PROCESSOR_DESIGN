#include <iostream>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <string>
#include <vector>
#include <cassert>

#include "core/isa.hpp"
#include "core/registers.hpp"
#include "core/memory.hpp"
#include "core/stack.hpp"
#include "core/pmc.hpp"
#include "alu/alu.hpp"
#include "pipelines/branch_predictor.hpp"
#include "pipelines/pipeline_4stage.hpp"
#include "pipelines/pipeline_6stage.hpp"
#include "control/microcode.hpp"
#include "toolchain/assembler.hpp"

using namespace risc201;

static std::string read_file_content(const std::string& filename) {
    std::vector<std::string> search_paths = {
        "programs/" + filename,
        "../programs/" + filename,
        "../../programs/" + filename,
        filename
    };

    for (const auto& path : search_paths) {
        std::ifstream file(path);
        if (file.is_open()) {
            std::stringstream buffer;
            buffer << file.rdbuf();
            return buffer.str();
        }
    }
    throw std::runtime_error("Could not find program file: " + filename);
}

static AssembledProgram load_program(const std::string& filename) {
    std::string src = read_file_content(filename);
    Assembler assembler;
    return assembler.assemble(src);
}

void benchmark_pipelines() {
    std::cout << "\n================================================================================\n";
    std::cout << " 1. COMPARATIVE PIPELINE EVALUATION: 4-STAGE vs. 6-STAGE PROCESSOR\n";
    std::cout << "================================================================================\n";

    std::vector<std::string> test_programs = {
        "01_basic_test.asm", "02_factorial.asm", "05_hazard_bench.asm", "06_branch_bench.asm"
    };

    std::cout << std::left
              << std::setw(20) << "Program" << " | "
              << std::setw(8)  << "Arch" << " | "
              << std::setw(8)  << "Cycles" << " | "
              << std::setw(8)  << "Insts" << " | "
              << std::setw(8)  << "Stalls" << " | "
              << std::setw(8)  << "CPI" << " | "
              << std::setw(8)  << "IPC" << "\n";
    std::cout << std::string(75, '-') << "\n";

    for (const auto& prog_name : test_programs) {
        AssembledProgram prog = load_program(prog_name);

        // 4-stage
        Processor4Stage cpu4(true);
        cpu4.memory.load_words(prog.text_start_addr, prog.text_words);
        if (!prog.data_bytes.empty()) {
            cpu4.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
        }
        cpu4.run();

        // 6-stage
        Processor6Stage cpu6(true);
        cpu6.memory.load_words(prog.text_start_addr, prog.text_words);
        if (!prog.data_bytes.empty()) {
            cpu6.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
        }
        cpu6.run();

        std::cout << std::fixed << std::setprecision(3);
        std::cout << std::left
                  << std::setw(20) << prog_name << " | "
                  << std::setw(8)  << "4-Stage" << " | "
                  << std::setw(8)  << cpu4.pmc.cycle_count << " | "
                  << std::setw(8)  << cpu4.pmc.instruction_count << " | "
                  << std::setw(8)  << cpu4.pmc.stall_count << " | "
                  << std::setw(8)  << cpu4.pmc.cpi() << " | "
                  << std::setw(8)  << cpu4.pmc.ipc() << "\n";

        std::cout << std::left
                  << std::setw(20) << prog_name << " | "
                  << std::setw(8)  << "6-Stage" << " | "
                  << std::setw(8)  << cpu6.pmc.cycle_count << " | "
                  << std::setw(8)  << cpu6.pmc.instruction_count << " | "
                  << std::setw(8)  << cpu6.pmc.stall_count << " | "
                  << std::setw(8)  << cpu6.pmc.cpi() << " | "
                  << std::setw(8)  << cpu6.pmc.ipc() << "\n";
        std::cout << std::string(75, '-') << "\n";
    }
}

void benchmark_forwarding() {
    std::cout << "\n================================================================================\n";
    std::cout << " 2. FORWARDING NETWORK IMPACT: FORWARDING ENABLED vs. DISABLED (05_hazard_bench.asm)\n";
    std::cout << "================================================================================\n";

    AssembledProgram prog = load_program("05_hazard_bench.asm");

    std::cout << std::left
              << std::setw(12) << "Architecture" << " | "
              << std::setw(10) << "Forwarding" << " | "
              << std::setw(8)  << "Cycles" << " | "
              << std::setw(8)  << "Stalls" << " | "
              << std::setw(8)  << "CPI" << " | "
              << std::setw(10) << "Fwd Events" << "\n";
    std::cout << std::string(68, '-') << "\n";

    // 4-Stage
    for (bool fwd : {true, false}) {
        Processor4Stage cpu(fwd);
        cpu.memory.load_words(prog.text_start_addr, prog.text_words);
        if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
        cpu.run();

        std::cout << std::fixed << std::setprecision(3) << std::left
                  << std::setw(12) << "4-Stage" << " | "
                  << std::setw(10) << (fwd ? "ON" : "OFF") << " | "
                  << std::setw(8)  << cpu.pmc.cycle_count << " | "
                  << std::setw(8)  << cpu.pmc.stall_count << " | "
                  << std::setw(8)  << cpu.pmc.cpi() << " | "
                  << std::setw(10) << cpu.pmc.forwarding_events << "\n";
    }

    // 6-Stage
    for (bool fwd : {true, false}) {
        Processor6Stage cpu(fwd);
        cpu.memory.load_words(prog.text_start_addr, prog.text_words);
        if (!prog.data_bytes.empty()) cpu.memory.load_bytes(prog.data_start_addr, prog.data_bytes);
        cpu.run();

        std::cout << std::fixed << std::setprecision(3) << std::left
                  << std::setw(12) << "6-Stage" << " | "
                  << std::setw(10) << (fwd ? "ON" : "OFF") << " | "
                  << std::setw(8)  << cpu.pmc.cycle_count << " | "
                  << std::setw(8)  << cpu.pmc.stall_count << " | "
                  << std::setw(8)  << cpu.pmc.cpi() << " | "
                  << std::setw(10) << cpu.pmc.forwarding_events << "\n";
    }
}

void benchmark_branch_predictors() {
    std::cout << "\n================================================================================\n";
    std::cout << " 3. BRANCH PREDICTOR EVALUATION: 2-BIT BTB vs. STATIC (06_branch_bench.asm)\n";
    std::cout << "================================================================================\n";

    AssembledProgram prog = load_program("06_branch_bench.asm");
    std::vector<std::pair<std::string, PredictorMode>> modes = {
        {"Dynamic 2-Bit + BTB", PredictorMode::DYNAMIC_2BIT},
        {"Static Always Not-Taken", PredictorMode::STATIC_NOT_TAKEN},
        {"Static Always Taken", PredictorMode::STATIC_TAKEN}
    };

    // 4-Stage
    std::cout << "\n--- 4-Stage Pipeline ---\n";
    std::cout << std::left
              << std::setw(25) << "Predictor Mode" << " | "
              << std::setw(8)  << "Cycles" << " | "
              << std::setw(10) << "Branches" << " | "
              << std::setw(12) << "Mispredicts" << " | "
              << std::setw(10) << "Mispred %" << " | "
              << std::setw(8)  << "CPI" << "\n";
    std::cout << std::string(85, '-') << "\n";

    for (const auto& [mode_name, mode] : modes) {
        Processor4Stage cpu(true, mode);
        cpu.memory.load_words(prog.text_start_addr, prog.text_words);
        cpu.run();
        const auto& pmc = cpu.pmc;
        std::stringstream ss;
        ss << std::fixed << std::setprecision(1) << pmc.branch_mispredict_rate() << "%";
        std::cout << std::fixed << std::setprecision(3) << std::left
                  << std::setw(25) << mode_name << " | "
                  << std::setw(8)  << pmc.cycle_count << " | "
                  << std::setw(10) << pmc.branch_count << " | "
                  << std::setw(12) << pmc.branch_mispredict_count << " | "
                  << std::setw(10) << ss.str() << " | "
                  << std::setw(8)  << pmc.cpi() << "\n";
    }

    // 6-Stage
    std::cout << "\n--- 6-Stage Pipeline ---\n";
    std::cout << std::left
              << std::setw(25) << "Predictor Mode" << " | "
              << std::setw(8)  << "Cycles" << " | "
              << std::setw(10) << "Branches" << " | "
              << std::setw(12) << "Mispredicts" << " | "
              << std::setw(10) << "Mispred %" << " | "
              << std::setw(8)  << "CPI" << "\n";
    std::cout << std::string(85, '-') << "\n";

    for (const auto& [mode_name, mode] : modes) {
        Processor6Stage cpu(true, mode);
        cpu.memory.load_words(prog.text_start_addr, prog.text_words);
        cpu.run();
        const auto& pmc = cpu.pmc;
        std::stringstream ss;
        ss << std::fixed << std::setprecision(1) << pmc.branch_mispredict_rate() << "%";
        std::cout << std::fixed << std::setprecision(3) << std::left
                  << std::setw(25) << mode_name << " | "
                  << std::setw(8)  << pmc.cycle_count << " | "
                  << std::setw(10) << pmc.branch_count << " | "
                  << std::setw(12) << pmc.branch_mispredict_count << " | "
                  << std::setw(10) << ss.str() << " | "
                  << std::setw(8)  << pmc.cpi() << "\n";
    }
}

void benchmark_microcode() {
    std::cout << "\n================================================================================\n";
    std::cout << " 4. CONTROL UNIT COMPARISON: HORIZONTAL vs. VERTICAL MICROPROGRAMMING\n";
    std::cout << "================================================================================\n";

    AssembledProgram prog = load_program("01_basic_test.asm");

    // Horizontal
    MicroprogrammedCPU cpu_h(false);
    cpu_h.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu_h.run();

    // Vertical
    MicroprogrammedCPU cpu_v(true);
    cpu_v.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu_v.run();

    std::cout << std::left
              << std::setw(32) << "Attribute" << " | "
              << std::setw(22) << "Horizontal Microcode" << " | "
              << std::setw(22) << "Vertical Microcode" << "\n";
    std::cout << std::string(80, '-') << "\n";
    std::cout << std::left
              << std::setw(32) << "Microinstruction Width" << " | "
              << std::setw(22) << "28 bits" << " | "
              << std::setw(22) << "14 bits" << "\n";
    std::cout << std::left
              << std::setw(32) << "Control Store ROM Capacity" << " | "
              << std::setw(22) << "28 x 82 = 2296 bits" << " | "
              << std::setw(22) << "14 x 82 = 1148 bits" << "\n";
    std::cout << std::left
              << std::setw(32) << "Decoding Overhead" << " | "
              << std::setw(22) << "None (Direct lines)" << " | "
              << std::setw(22) << "Requires micro-decoders" << "\n";
    std::cout << std::left
              << std::setw(32) << "Total Micro-Cycles Executed" << " | "
              << std::setw(22) << std::to_string(cpu_h.total_micro_cycles) << " | "
              << std::setw(22) << std::to_string(cpu_v.total_micro_cycles) << "\n";
    std::cout << std::left
              << std::setw(32) << "Macro Instructions Committed" << " | "
              << std::setw(22) << std::to_string(cpu_h.pmc.instruction_count) << " | "
              << std::setw(22) << std::to_string(cpu_v.pmc.instruction_count) << "\n";

    double avg_micro_cpi = cpu_h.pmc.instruction_count ? (static_cast<double>(cpu_h.total_micro_cycles) / cpu_h.pmc.instruction_count) : 0.0;
    std::stringstream ss;
    ss << std::fixed << std::setprecision(2) << avg_micro_cpi;
    std::cout << std::left
              << std::setw(32) << "Micro-Cycles Per Instruction" << " | "
              << std::setw(22) << ss.str() << " | "
              << std::setw(22) << ss.str() << "\n";
}

void benchmark_alu_algorithms() {
    std::cout << "\n================================================================================\n";
    std::cout << " 5. ALU ALGORITHMIC EVALUATION: MULTIPLIER & DIVIDER MODELS\n";
    std::cout << "================================================================================\n";

    ALU alu_fast(MultiplierAlgorithm::FAST, DividerAlgorithm::FAST);
    ALU alu_booth(MultiplierAlgorithm::BOOTH, DividerAlgorithm::RESTORING);
    ALU alu_shift(MultiplierAlgorithm::SHIFT_AND_ADD, DividerAlgorithm::RESTORING);

    std::vector<std::pair<int32_t, int32_t>> test_multiplications = {
        {12, 10}, {-7, 8}, {1234, 5678}, {-25, -25}
    };
    std::cout << "\n--- Multiplication Algorithms ---\n";
    for (const auto& [a, b] : test_multiplications) {
        int32_t r_fast = alu_fast.execute(Opcode::MUL, a, b);
        int32_t r_booth = alu_booth.execute(Opcode::MUL, a, b);
        int32_t r_shift = alu_shift.execute(Opcode::MUL, a, b);
        std::cout << " " << std::right << std::setw(6) << a << " * " << std::setw(6) << b
                  << " = " << std::setw(10) << r_fast
                  << " | Fast: 1 cycle | Booth: 32 cycles (" << r_booth << ") | Shift-Add: 32 cycles (" << r_shift << ")\n";
    }

    std::vector<std::pair<int32_t, int32_t>> test_divisions = {
        {100, 5}, {1234, 10}, {-50, 7}, {1000, -25}
    };
    std::cout << "\n--- Division Algorithms ---\n";
    for (const auto& [a, b] : test_divisions) {
        int32_t d_fast = alu_fast.execute(Opcode::DIV, a, b);
        int32_t d_rest = alu_booth.execute(Opcode::DIV, a, b);
        std::cout << " " << std::right << std::setw(6) << a << " / " << std::setw(6) << b
                  << " = " << std::setw(10) << d_fast
                  << " | Fast: 1 cycle | Restoring: 32 cycles (" << d_rest << ")\n";
    }
}

void benchmark_security_canary() {
    std::cout << "\n================================================================================\n";
    std::cout << " 6. SECURITY & RUNTIME EXCEPTION TRAPPING: STACK CANARY OVERFLOW CHECK\n";
    std::cout << "================================================================================\n";

    AssembledProgram prog = load_program("04_buffer_overflow.asm");
    Processor4Stage cpu;
    cpu.memory.load_words(prog.text_start_addr, prog.text_words);

    std::cout << "[*] Launching vulnerable function exploit test (04_buffer_overflow.asm)...\n";
    cpu.run();

    if (cpu.exception_raised && cpu.last_exception) {
        std::cout << "[🛡️ SECURITY SYSTEM ACTIVE] Stack tampering prevented!\n";
        std::cout << "  Captured Exception : " << cpu.last_exception->message << "\n";
        std::cout << "  Trap Cause Code    : " << static_cast<int>(cpu.csr.cause) << " (" << get_cause_name(cpu.csr.cause) << ")\n";
        std::cout << "  Faulting EPC       : 0x" << std::hex << std::uppercase << std::setw(8) << std::setfill('0') << cpu.csr.epc << "\n";
        std::cout << "  Processor Status   : " << cpu.csr.to_dict()["STATUS"] << "\n";
        assert(cpu.csr.cause == CSRCause::STACK_CANARY_CORRUPTED && "Should be STACK_CANARY_CORRUPTED");
        std::cout << "[✓] Stack Canary Protection & CSR Exception Framework successfully verified!\n";
    } else {
        std::cout << "[!] Warning: Buffer overflow was not caught!\n";
    }
}

void benchmark_leaf_optimization() {
    std::cout << std::dec << std::setfill(' ');
    std::cout << "\n================================================================================\n";
    std::cout << " 7. LEAF FUNCTION OPTIMIZATION IMPACT (Standard Frame vs. Leaf Optimized)\n";
    std::cout << "================================================================================\n";

    std::string code_std =
        ".text\n"
        ".globl main\n"
        "main:\n"
        "    mov r1, 10\n"
        "    mov r2, 0\n"
        "    mov r3, 1\n"
        ".loop:\n"
        "    cmp r3, r1\n"
        "    bgt .done\n"
        "    mov r10, r3\n"
        "    call std_square\n"
        "    add r2, r2, r4\n"
        "    add r3, r3, 1\n"
        "    b .loop\n"
        ".done:\n"
        "    mov r1, r2\n"
        "    hlt\n"
        "std_square:\n"
        "    enter 0\n"
        "    mul r4, r10, r10\n"
        "    leave 0\n";

    Assembler asm_obj;
    AssembledProgram prog_std = asm_obj.assemble(code_std);
    Processor6Stage cpu_std;
    cpu_std.memory.load_words(prog_std.text_start_addr, prog_std.text_words);
    cpu_std.run();

    AssembledProgram prog_leaf = load_program("08_leaf_bench.asm");
    Processor6Stage cpu_leaf;
    cpu_leaf.memory.load_words(prog_leaf.text_start_addr, prog_leaf.text_words);
    cpu_leaf.run();

    std::cout << std::left
              << std::setw(30) << "Subroutine Convention" << " | "
              << std::setw(12) << "Total Cycles" << " | "
              << std::setw(12) << "Instructions" << " | "
              << std::setw(8)  << "CPI" << "\n";
    std::cout << std::string(70, '-') << "\n";
    std::cout << std::left
              << std::setw(30) << "Standard Frame (RA+FP+Canary)" << " | "
              << std::setw(12) << cpu_std.pmc.cycle_count << " | "
              << std::setw(12) << cpu_std.pmc.instruction_count << " | "
              << std::fixed << std::setprecision(3) << cpu_std.pmc.cpi() << "\n";
    std::cout << std::left
              << std::setw(30) << "Leaf Optimized (No RA/FP)" << " | "
              << std::setw(12) << cpu_leaf.pmc.cycle_count << " | "
              << std::setw(12) << cpu_leaf.pmc.instruction_count << " | "
              << std::fixed << std::setprecision(3) << cpu_leaf.pmc.cpi() << "\n";
    std::cout << std::string(70, '-') << "\n";
    double cycle_diff = cpu_std.pmc.cycle_count - cpu_leaf.pmc.cycle_count;
    double speedup = static_cast<double>(cpu_std.pmc.cycle_count) / cpu_leaf.pmc.cycle_count;
    std::cout << "[*] Cycle Reduction: " << static_cast<int>(cycle_diff) << " cycles ("
              << std::fixed << std::setprecision(1) << (cycle_diff / cpu_std.pmc.cycle_count * 100.0)
              << "% savings, " << std::setprecision(2) << speedup << "x speedup)\n";
    std::cout << "[*] Memory Traffic: Eliminates 6 stack memory operations per function call.\n";
}

#ifndef NO_BENCHMARK_MAIN
int main() {
    benchmark_pipelines();
    benchmark_forwarding();
    benchmark_branch_predictors();
    benchmark_microcode();
    benchmark_alu_algorithms();
    benchmark_security_canary();
    benchmark_leaf_optimization();
    std::cout << "\n================================================================================\n";
    std::cout << " ALL BENCHMARK EVALUATIONS COMPLETED SUCCESSFULLY.\n";
    std::cout << "================================================================================\n\n";
    return 0;
}
#endif
