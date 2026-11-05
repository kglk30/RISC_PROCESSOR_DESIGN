#include <iostream>
#include <cassert>
#include <string>
#include <vector>

#include "core/isa.hpp"
#include "core/registers.hpp"
#include "core/memory.hpp"
#include "core/stack.hpp"
#include "core/pmc.hpp"
#include "alu/alu.hpp"
#include "pipelines/pipeline_4stage.hpp"
#include "pipelines/pipeline_6stage.hpp"
#include "control/microcode.hpp"
#include "toolchain/assembler.hpp"
#include "toolchain/disassembler.hpp"

using namespace risc201;

static int g_tests_run = 0;
static int g_tests_passed = 0;

#define TEST_ASSERT(cond, msg) \
    do { \
        if (!(cond)) { \
            std::cerr << "[-] Assertion FAILED: " << msg << " (" << __FILE__ << ":" << __LINE__ << ")\n"; \
            return false; \
        } \
    } while (0)

bool test_hardwired_r0() {
    std::cout << "[RUNNING] test_hardwired_r0...\n";
    RegisterFile rf;
    rf.reset();
    TEST_ASSERT(rf.read(0) == 0, "r0 must be initially 0");

    rf.write(0, 100);
    TEST_ASSERT(rf.read(0) == 0, "r0 must ignore writes");
    rf.write(0, -9999);
    TEST_ASSERT(rf.read(0) == 0, "r0 must remain 0");

    rf.write(1, 42);
    TEST_ASSERT(rf.read(1) == 42, "r1 must store written value");

    std::cout << " [PASS] test_hardwired_r0\n";
    return true;
}

bool test_alu_operations() {
    std::cout << "[RUNNING] test_alu_operations...\n";
    ALU alu;
    
    // ADD
    int32_t res = alu.execute(Opcode::ADD, 15, 25);
    TEST_ASSERT(res == 40, "ADD 15, 25 must be 40");
    TEST_ASSERT(!alu.flags.Z, "Zero flag must not be set");
    TEST_ASSERT(!alu.flags.N, "Negative flag must not be set");

    // SUB and Zero flag
    res = alu.execute(Opcode::SUB, 25, 25);
    TEST_ASSERT(res == 0, "SUB 25, 25 must be 0");
    TEST_ASSERT(alu.flags.Z, "Zero flag must be set");

    // Negative flag
    res = alu.execute(Opcode::SUB, 10, 20);
    TEST_ASSERT(res == -10, "SUB 10, 20 must be -10");
    TEST_ASSERT(alu.flags.N, "Negative flag must be set");

    // MUL fast
    res = alu.execute(Opcode::MUL, 6, 7);
    TEST_ASSERT(res == 42, "MUL 6, 7 must be 42");

    // MUL Booth's algorithm
    ALU alu_booth(MultiplierAlgorithm::BOOTH, DividerAlgorithm::FAST);
    res = alu_booth.execute(Opcode::MUL, 12, -4);
    TEST_ASSERT(res == -48, "Booth MUL 12, -4 must be -48");

    // DIV Restoring
    ALU alu_div(MultiplierAlgorithm::FAST, DividerAlgorithm::RESTORING);
    res = alu_div.execute(Opcode::DIV, 100, 4);
    TEST_ASSERT(res == 25, "Restoring DIV 100, 4 must be 25");

    // Division by zero
    bool div_zero_caught = false;
    try {
        alu.execute(Opcode::DIV, 10, 0);
    } catch (const DivisionByZeroException&) {
        div_zero_caught = true;
    }
    TEST_ASSERT(div_zero_caught, "Division by zero must throw DivisionByZeroException");

    // Logic & Shifts
    TEST_ASSERT(alu.execute(Opcode::AND, 0b1100, 0b1010) == 0b1000, "AND failed");
    TEST_ASSERT(alu.execute(Opcode::OR, 0b1100, 0b1010) == 0b1110, "OR failed");
    TEST_ASSERT(alu.execute(Opcode::LSL, 5, 2) == 20, "LSL failed");
    TEST_ASSERT(alu.execute(Opcode::ASR, -16, 2) == -4, "ASR failed");

    std::cout << " [PASS] test_alu_operations\n";
    return true;
}

bool test_memory_safety() {
    std::cout << "[RUNNING] test_memory_safety...\n";
    Memory mem(0x10000);
    mem.write_word(0x1000, 0x12345678);
    TEST_ASSERT(mem.read_word(0x1000) == 0x12345678, "Memory read/write mismatch");

    // Misalignment check
    bool misaligned_caught = false;
    try {
        mem.read_word(0x1001);
    } catch (const CPUException& ex) {
        misaligned_caught = (ex.cause == CSRCause::MISALIGNED_ACCESS);
    }
    TEST_ASSERT(misaligned_caught, "Misaligned memory read must raise MISALIGNED_ACCESS");

    // Red Zone guard check
    bool redzone_caught = false;
    try {
        mem.write_word(0x00002F00, static_cast<int32_t>(0xCAFEBABE));
    } catch (const CPUException& ex) {
        redzone_caught = (ex.cause == CSRCause::STACK_OVERFLOW);
    }
    TEST_ASSERT(redzone_caught, "Writing into Red Zone must raise STACK_OVERFLOW");

    std::cout << " [PASS] test_memory_safety\n";
    return true;
}

bool test_assembler_disassembler() {
    std::cout << "[RUNNING] test_assembler_disassembler...\n";
    std::string asm_code = 
        ".text\n"
        "main:\n"
        "    add r1, r2, r3\n"
        "    ld r4, 16[r5]\n"
        "    st r6, 0[sp]\n"
        "    beq target\n"
        "    nop\n"
        "target:\n"
        "    hlt\n";

    Assembler assembler;
    AssembledProgram prog = assembler.assemble(asm_code);
    TEST_ASSERT(prog.text_words.size() == 6, "Expected 6 instructions");

    std::string dis0 = Disassembler::disassemble_word(prog.text_words[0], 0x00);
    TEST_ASSERT(dis0 == "add r1, r2, r3", "Disassembly mismatch for inst 0: " + dis0);

    std::string dis1 = Disassembler::disassemble_word(prog.text_words[1], 0x04);
    TEST_ASSERT(dis1 == "ld r4, 16[r5]", "Disassembly mismatch for inst 1: " + dis1);

    std::string dis2 = Disassembler::disassemble_word(prog.text_words[2], 0x08);
    TEST_ASSERT(dis2 == "st r6, 0[sp]", "Disassembly mismatch for inst 2: " + dis2);

    std::cout << " [PASS] test_assembler_disassembler\n";
    return true;
}

bool test_pipeline_4stage_execution() {
    std::cout << "[RUNNING] test_pipeline_4stage_execution...\n";
    std::string code = 
        ".text\n"
        "mov r1, 10\n"
        "mov r2, 20\n"
        "add r3, r1, r2\n"
        "sub r4, r3, 5\n"
        "hlt\n";

    Assembler assembler;
    AssembledProgram prog = assembler.assemble(code);

    Processor4Stage cpu;
    cpu.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu.run();

    TEST_ASSERT(cpu.halted, "CPU must be halted");
    TEST_ASSERT(cpu.rf.read(1) == 10, "r1 must be 10");
    TEST_ASSERT(cpu.rf.read(2) == 20, "r2 must be 20");
    TEST_ASSERT(cpu.rf.read(3) == 30, "r3 must be 30");
    TEST_ASSERT(cpu.rf.read(4) == 25, "r4 must be 25");

    std::cout << " [PASS] test_pipeline_4stage_execution\n";
    return true;
}

bool test_pipeline_6stage_execution() {
    std::cout << "[RUNNING] test_pipeline_6stage_execution...\n";
    std::string code = 
        ".text\n"
        "mov r1, 7\n"
        "mov r2, 8\n"
        "mul r3, r1, r2\n"
        "add r4, r3, r0\n"
        "hlt\n";

    Assembler assembler;
    AssembledProgram prog = assembler.assemble(code);

    Processor6Stage cpu;
    cpu.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu.run();

    TEST_ASSERT(cpu.halted, "CPU must be halted");
    TEST_ASSERT(cpu.rf.read(3) == 56, "r3 must be 56");
    TEST_ASSERT(cpu.rf.read(4) == 56, "r4 must be 56");

    std::cout << " [PASS] test_pipeline_6stage_execution\n";
    return true;
}

bool test_microcode_execution() {
    std::cout << "[RUNNING] test_microcode_execution...\n";
    std::string code = 
        ".text\n"
        "mov r1, 15\n"
        "mov r2, 3\n"
        "div r3, r1, r2\n"
        "mod r4, r1, r2\n"
        "hlt\n";

    Assembler assembler;
    AssembledProgram prog = assembler.assemble(code);

    // Horizontal
    {
        MicroprogrammedCPU cpu_h(false);
        cpu_h.memory.load_words(prog.text_start_addr, prog.text_words);
        cpu_h.run();
        TEST_ASSERT(cpu_h.rf.read(3) == 5, "Horizontal: r3 must be 5");
        TEST_ASSERT(cpu_h.rf.read(4) == 0, "Horizontal: r4 must be 0");
    }

    // Vertical
    {
        MicroprogrammedCPU cpu_v(true);
        cpu_v.memory.load_words(prog.text_start_addr, prog.text_words);
        cpu_v.run();
        TEST_ASSERT(cpu_v.rf.read(3) == 5, "Vertical: r3 must be 5");
        TEST_ASSERT(cpu_v.rf.read(4) == 0, "Vertical: r4 must be 0");
    }

    std::cout << " [PASS] test_microcode_execution\n";
    return true;
}

bool test_stack_canary_protection() {
    std::cout << "[RUNNING] test_stack_canary_protection...\n";
    std::string code = 
        ".text\n"
        "main:\n"
        "    call test_vuln\n"
        "    hlt\n"
        "test_vuln:\n"
        "    enter 4\n"
        "    ; Smash the canary at 4[sp]\n"
        "    mov r2, 0x11223344\n"
        "    st r2, 4[sp]\n"
        "    leave 4\n";

    Assembler assembler;
    AssembledProgram prog = assembler.assemble(code);

    Processor4Stage cpu;
    cpu.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu.run();

    TEST_ASSERT(cpu.exception_raised, "Exception must be raised on smashed canary");
    TEST_ASSERT(cpu.csr.cause == CSRCause::STACK_CANARY_CORRUPTED, "Cause must be STACK_CANARY_CORRUPTED");

    std::cout << " [PASS] test_stack_canary_protection\n";
    return true;
}

bool test_leaf_function_optimization() {
    std::cout << "[RUNNING] test_leaf_function_optimization...\n";
    // 1. Preprocessor test
    StackPreprocessor sp;
    std::vector<std::string> lines = {
        "my_leaf: enter_leaf 0",
        "add r1, r1, 10",
        "leave_leaf 0"
    };
    auto expanded = sp.expand_lines(lines);
    for (const auto& l : expanded) {
        TEST_ASSERT(l.find("st ra") == std::string::npos, "Leaf function must not save ra");
        TEST_ASSERT(l.find("st fp") == std::string::npos, "Leaf function must not save fp");
        TEST_ASSERT(l.find("ld fp") == std::string::npos, "Leaf function must not restore fp");
        TEST_ASSERT(l.find("ld ra") == std::string::npos, "Leaf function must not restore ra");
    }

    // 2. Execution test
    std::string code = 
        ".text\n"
        "main:\n"
        "    mov r1, 15\n"
        "    call leaf_add\n"
        "    hlt\n"
        "leaf_add:\n"
        "    enter_leaf 0\n"
        "    add r1, r1, 10\n"
        "    leave_leaf 0\n";

    Assembler assembler;
    AssembledProgram prog = assembler.assemble(code);

    Processor4Stage cpu4;
    cpu4.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu4.run();
    TEST_ASSERT(cpu4.rf.read(1) == 25, "4-Stage: Leaf function result must be 25");

    Processor6Stage cpu6;
    cpu6.memory.load_words(prog.text_start_addr, prog.text_words);
    cpu6.run();
    TEST_ASSERT(cpu6.rf.read(1) == 25, "6-Stage: Leaf function result must be 25");

    std::cout << " [PASS] test_leaf_function_optimization\n";
    return true;
}

int main() {
    std::cout << "================================================================\n";
    std::cout << " RISC201 Processor Simulation Environment - C++ Test Suite\n";
    std::cout << "================================================================\n";

    auto run_test = [](bool (*test_fn)()) {
        g_tests_run++;
        if (test_fn()) {
            g_tests_passed++;
        }
    };

    run_test(test_hardwired_r0);
    run_test(test_alu_operations);
    run_test(test_memory_safety);
    run_test(test_assembler_disassembler);
    run_test(test_pipeline_4stage_execution);
    run_test(test_pipeline_6stage_execution);
    run_test(test_microcode_execution);
    run_test(test_stack_canary_protection);
    run_test(test_leaf_function_optimization);

    std::cout << "================================================================\n";
    std::cout << " Summary: " << g_tests_passed << " / " << g_tests_run << " tests passed.\n";
    if (g_tests_passed == g_tests_run) {
        std::cout << " [✓] ALL UNIT TESTS COMPLETED SUCCESSFULLY!\n";
        std::cout << "================================================================\n";
        return 0;
    } else {
        std::cerr << " [X] SOME TESTS FAILED!\n";
        std::cout << "================================================================\n";
        return 1;
    }
}
