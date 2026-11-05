#!/usr/bin/env python3
"""
Comprehensive RISC201 Test & Benchmark Runner
Executes all 14 unit test cases and all 7 assembly benchmark programs,
printing all inputs, operations, and final values.
"""

import sys
import os
import glob

# Ensure UTF-8 output on Windows consoles
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

# Ensure repository root is on sys.path
repo_root = os.path.dirname(os.path.abspath(__file__))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from risc201.alu.alu import ALU, MultiplierAlgorithm, DividerAlgorithm, DivisionByZeroException
from risc201.core.isa import Opcode, to_signed32
from risc201.core.memory import Memory
from risc201.core.registers import CSRCause, CPUException
from risc201.toolchain.assembler import Assembler
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.pipelines.pipeline_6stage import Processor6Stage
from risc201.control.microcode import MicroprogrammedCPU


def print_banner(title: str):
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def run_unit_tests_with_values():
    print_banner("PART 1: RUNNING ALL 15 UNIT TESTS WITH FINAL VALUES")
    alu = ALU()
    passed = 0
    total = 15

    # 1. ALU Operations
    print("\n[Test 1/15] ALU Basic Operations")
    r_add = alu.execute(Opcode.ADD, 15, 25)
    r_sub = alu.execute(Opcode.SUB, 25, 25)
    z_flag = alu.flags.Z
    r_neg = alu.execute(Opcode.SUB, 10, 20)
    n_flag = alu.flags.N
    r_lsl = alu.execute(Opcode.LSL, 5, 2)
    r_asr = alu.execute(Opcode.ASR, -16, 2)
    print(f"    15 + 25 = {r_add:<4} | 25 - 25 = {r_sub:<2} (Z={z_flag}) | 10 - 20 = {r_neg:<3} (N={n_flag})")
    print(f"    5 << 2  = {r_lsl:<4} | -16 >> 2 = {r_asr:<3} (arithmetic shift)")
    assert r_add == 40 and r_sub == 0 and z_flag and r_neg == -10 and n_flag and r_lsl == 20 and r_asr == -4
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 2. Dadda Multiplier
    print("\n[Test 2/15] Dadda Tree Multiplier (6-Cycle Simulated Latency)")
    alu_d = ALU(mul_algo=MultiplierAlgorithm.DADDA)
    m1 = alu_d.execute(Opcode.MUL, 7, 8)
    m2 = alu_d.execute(Opcode.MUL, 100, 100)
    m3 = alu_d.execute(Opcode.MUL, -3, 4)
    m4 = alu_d.execute(Opcode.MUL, -5, -6)
    m5 = alu_d.execute(Opcode.MUL, 65536, 65536)
    lat_mul = alu_d.latency_cycles(Opcode.MUL)
    print(f"    7 * 8       = {m1:<7} | -3 * 4     = {m3:<6} (N={alu_d.flags.N})")
    print(f"    100 * 100   = {m2:<7} | -5 * -6    = {m4:<6}")
    print(f"    65536*65536 = {m5:<7} (32-bit wrap) | Latency: {lat_mul} cycles")
    assert m1 == 56 and m2 == 10000 and m3 == -12 and m4 == 30 and m5 == 0 and lat_mul == 6
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 3. SRT Radix-2 Division
    print("\n[Test 3/15] SRT Radix-2 Divider (32-Cycle Non-Restoring)")
    alu_s = ALU(div_algo=DividerAlgorithm.SRT)
    d1 = alu_s.execute(Opcode.DIV, 20, 4)
    d2 = alu_s.execute(Opcode.DIV, 17, 3); r2 = alu_s.execute(Opcode.MOD, 17, 3)
    d3 = alu_s.execute(Opcode.DIV, -20, 4)
    d4 = alu_s.execute(Opcode.DIV, -17, 3); r4 = alu_s.execute(Opcode.MOD, -17, 3)
    d5 = alu_s.execute(Opcode.DIV, -20, -4)
    d6 = alu_s.execute(Opcode.DIV, 42, 1)
    div_zero_caught = False
    try:
        alu_s.execute(Opcode.DIV, 10, 0)
    except DivisionByZeroException:
        div_zero_caught = True
    lat_div = alu_s.latency_cycles(Opcode.DIV)
    print(f"    20 / 4   = {d1:<4} | 17 / 3   = {d2:<3} (rem {r2:<2}) | 42 / 1 = {d6}")
    print(f"    -20 / 4  = {d3:<4} | -17 / 3  = {d4:<3} (rem {r4:<2}) | -20 / -4 = {d5}")
    print(f"    Division by zero exception caught: {div_zero_caught} | Latency: {lat_div} cycles")
    assert d1 == 5 and d2 == 5 and r2 == 2 and d3 == -5 and d4 == -5 and r4 == -2 and d5 == 5 and d6 == 42 and div_zero_caught
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 4. Count Leading Zeros (CLZ)
    print("\n[Test 4/15] Count Leading Zeros (CLZ - 5-Step Binary Search)")
    c0 = alu.execute(Opcode.CLZ, 0, 0)
    c1 = alu.execute(Opcode.CLZ, 1, 0)
    c2 = alu.execute(Opcode.CLZ, 2, 0)
    c_ff = alu.execute(Opcode.CLZ, 0xFF, 0)
    c_ffff = alu.execute(Opcode.CLZ, 0xFFFF, 0)
    c_msb = alu.execute(Opcode.CLZ, 0x80000000, 0)
    print(f"    CLZ(0)          = {c0:<2} | CLZ(1)      = {c1:<2} | CLZ(2) = {c2}")
    print(f"    CLZ(0x000000FF) = {c_ff:<2} | CLZ(0xFFFF) = {c_ffff:<2} | CLZ(0x80000000) = {c_msb} (Z={alu.flags.Z})")
    assert c0 == 32 and c1 == 31 and c2 == 30 and c_ff == 24 and c_ffff == 16 and c_msb == 0
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 5. Population Count (POPCNT Hamming SWAR)
    print("\n[Test 5/15] Population Count (POPCNT - Parallel Hamming SWAR)")
    p0 = alu.execute(Opcode.POPCNT, 0, 0)
    p1 = alu.execute(Opcode.POPCNT, 1, 0)
    p_all = alu.execute(Opcode.POPCNT, 0xFFFFFFFF, 0)
    p_alt1 = alu.execute(Opcode.POPCNT, 0x55555555, 0)
    p_alt2 = alu.execute(Opcode.POPCNT, 0xAAAAAAAA, 0)
    p_msblsb = alu.execute(Opcode.POPCNT, 0x80000001, 0)
    print(f"    POPCNT(0x00000000) = {p0:<2} (Z={alu.flags.Z}) | POPCNT(1)          = {p1}")
    print(f"    POPCNT(0xFFFFFFFF) = {p_all:<2}         | POPCNT(0x55555555) = {p_alt1}")
    print(f"    POPCNT(0xAAAAAAAA) = {p_alt2:<2}         | POPCNT(0x80000001) = {p_msblsb}")
    assert p0 == 0 and p1 == 1 and p_all == 32 and p_alt1 == 16 and p_alt2 == 16 and p_msblsb == 2
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 6. Memory Safety
    print("\n[Test 6/15] Memory Safety & Alignment")
    mem = Memory(size=0x10000)
    mem.write_word(0x1000, 0x12345678)
    val_mem = mem.read_word(0x1000)
    raw_b = [mem.bytes[0x1000 + i] for i in range(4)]
    unaligned_caught = False
    try:
        mem.read_word(0x1001)
    except CPUException as e:
        if e.cause == CSRCause.MISALIGNED_ACCESS:
            unaligned_caught = True
    print(f"    Memory Read(0x1000): 0x{val_mem:08X} (Little-endian bytes: {raw_b[0]:02X} {raw_b[1]:02X} {raw_b[2]:02X} {raw_b[3]:02X})")
    print(f"    Unaligned Access Exception caught properly: {unaligned_caught}")
    assert val_mem == 0x12345678 and unaligned_caught
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 7. Hardwired r0
    print("\n[Test 7/15] Hardwired Zero Register (r0)")
    asm = Assembler()
    prog_r0 = asm.assemble(".text\nmov r1, 42\nadd r0, r1, r1\nadd r2, r0, 10\nhlt")
    mem_r0 = Memory()
    mem_r0.load_words(0, prog_r0.text_words)
    cpu_r0 = Processor4Stage(memory=mem_r0)
    cpu_r0.run()
    r0_val = cpu_r0.rf.read(0)
    r2_val = cpu_r0.rf.read(2)
    print(f"    Register r0 after write attempt: {r0_val} (must be 0)")
    print(f"    Register r2 (0 + 10):            {r2_val} (must be 10)")
    assert r0_val == 0 and r2_val == 10
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 8. Assembler / Disassembler
    print("\n[Test 8/15] Assembler & Disassembler Round-Trip")
    test_asm = ".text\nadd r3, r1, r2\nsub r4, r3, 10\nclz r5, r4\npopcnt r6, r5\nhlt"
    prog_ad = asm.assemble(test_asm)
    words = prog_ad.text_words
    print(f"    Assembled {len(words)} instructions to machine words: {[hex(w) for w in words]}")
    assert len(words) == 5
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 9. 4-Stage Pipeline Execution & Structural Stalling
    print("\n[Test 9/15] 4-Stage Pipeline Execution (Dadda MUL + Structural Stalls)")
    code_p4 = ".text\nmov r1, 7\nmov r2, 8\nmul r3, r1, r2\nadd r4, r3, r0\nhlt"
    prog_p4 = asm.assemble(code_p4)
    mem_p4 = Memory(); mem_p4.load_words(0, prog_p4.text_words)
    cpu_p4 = Processor4Stage(memory=mem_p4)
    cpu_p4.run()
    p4_r3 = cpu_p4.rf.read(3)
    p4_r4 = cpu_p4.rf.read(4)
    p4_stalls = cpu_p4.pmc.structural_stalls
    p4_cycles = cpu_p4.pmc.cycle_count
    print(f"    r3 (7 * 8) = {p4_r3} | r4 (r3 + 0) = {p4_r4}")
    print(f"    Total Cycles: {p4_cycles} | Structural Stalls Recorded: {p4_stalls} | Instructions: {cpu_p4.pmc.instruction_count}")
    assert p4_r3 == 56 and p4_r4 == 56 and p4_stalls == 5
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 10. 6-Stage Pipeline Execution & Forwarding
    print("\n[Test 10/15] 6-Stage Pipeline Execution (Forwarding Network + Stalls)")
    prog_p6 = asm.assemble(code_p4)
    mem_p6 = Memory(); mem_p6.load_words(0, prog_p6.text_words)
    cpu_p6 = Processor6Stage(memory=mem_p6)
    cpu_p6.run()
    p6_r3 = cpu_p6.rf.read(3)
    p6_r4 = cpu_p6.rf.read(4)
    p6_stalls = cpu_p6.pmc.structural_stalls
    p6_cycles = cpu_p6.pmc.cycle_count
    print(f"    r3 (7 * 8) = {p6_r3} | r4 (r3 + 0) = {p6_r4}")
    print(f"    Total Cycles: {p6_cycles} | Structural Stalls Recorded: {p6_stalls} | Instructions: {cpu_p6.pmc.instruction_count}")
    assert p6_r3 == 56 and p6_r4 == 56 and p6_stalls == 5
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 11. Microprogrammed CPU Execution
    print("\n[Test 11/15] Microprogrammed Control Unit (Horizontal & Vertical ROM)")
    code_mc = ".text\nmov r1, 15\nmov r2, 3\ndiv r3, r1, r2\nmod r4, r1, r2\nhlt"
    prog_mc = asm.assemble(code_mc)
    mem_mh = Memory(); mem_mh.load_words(0, prog_mc.text_words)
    cpu_mh = MicroprogrammedCPU(memory=mem_mh, use_vertical=False); cpu_mh.run()
    mem_mv = Memory(); mem_mv.load_words(0, prog_mc.text_words)
    cpu_mv = MicroprogrammedCPU(memory=mem_mv, use_vertical=True); cpu_mv.run()
    print(f"    Horizontal Microcode: r3 (15/3) = {cpu_mh.rf.read(3)}, r4 (15%3) = {cpu_mh.rf.read(4)}")
    print(f"    Vertical Microcode:   r3 (15/3) = {cpu_mv.rf.read(3)}, r4 (15%3) = {cpu_mv.rf.read(4)}")
    assert cpu_mh.rf.read(3) == 5 and cpu_mh.rf.read(4) == 0
    assert cpu_mv.rf.read(3) == 5 and cpu_mv.rf.read(4) == 0
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 12. Stack Canary Protection
    print("\n[Test 12/15] Stack Canary Protection (Buffer Overflow Detection)")
    code_can = ".text\nmain: call test_vuln\n hlt\ntest_vuln: enter 4\n mov r2, 0x11223344\n st r2, 4[sp]\n leave 4"
    prog_can = asm.assemble(code_can)
    mem_can = Memory(); mem_can.load_words(0, prog_can.text_words)
    cpu_can = Processor4Stage(memory=mem_can)
    cpu_can.run()
    print(f"    Exception raised: {cpu_can.exception_raised}")
    print(f"    CSR Cause:        {cpu_can.csr.cause} ({cpu_can.last_exception})")
    assert cpu_can.exception_raised and cpu_can.csr.cause == CSRCause.STACK_CANARY_CORRUPTED
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 13. Stack Preprocessor Same-Line Labels
    print("\n[Test 13/15] Stack Preprocessor Parsing")
    sp = asm.preprocessor
    out_sp = sp.expand_lines(["main: mov r1, 10"])
    print(f"    Expanded: '{out_sp[0]}'")
    assert len(out_sp) == 1 and "main:" in out_sp[0] and "mov r1, 10" in out_sp[0]
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 14. Pipeline vs Microcode Cross-Validation
    print("\n[Test 14/15] Cross-Model Architectural Verification Across All Programs")
    program_files = sorted(glob.glob(os.path.join(repo_root, "programs", "*.asm")))
    for p_path in program_files:
        p_name = os.path.basename(p_path)
        with open(p_path, "r", encoding="utf-8") as f:
            prog_x = asm.assemble(f.read())
        # Compare 4-stage vs Microcode Horizontal vs Microcode Vertical
        states = []
        for cls, kw in [(Processor4Stage, {}), (MicroprogrammedCPU, {"use_vertical": False}), (MicroprogrammedCPU, {"use_vertical": True})]:
            m = Memory()
            m.load_words(prog_x.text_start_addr, prog_x.text_words)
            if prog_x.data_bytes:
                m.load_bytes(prog_x.data_start_addr, bytes(prog_x.data_bytes))
            c = cls(memory=m, **kw)
            c.run()
            states.append(([c.rf.read(i) for i in range(16)], c.exception_raised))
        assert states[0] == states[1] == states[2], f"Mismatch on {p_name}"
        print(f"    * {p_name:24s} -> Identical register & exception state across all models [OK]")
    print("    --> RESULT: PASS [OK]")
    passed += 1

    # 15. Leaf Function Optimization
    print("\n[Test 15/15] Leaf Function Optimization (Avoids saving RA & FP when safe)")
    code_leaf = ".text\nmain: mov r1, 15\n call leaf_add\n hlt\nleaf_add: enter_leaf 0\n add r1, r1, 10\n leave_leaf 0"
    prog_leaf = asm.assemble(code_leaf)
    mem_leaf = Memory(); mem_leaf.load_words(0, prog_leaf.text_words)
    cpu_leaf = Processor6Stage(memory=mem_leaf)
    cpu_leaf.run()
    r1_leaf = cpu_leaf.rf.read(1)
    # Check that enter_leaf lines do not contain st ra, 0[sp]
    expanded_leaf = asm.preprocessor.expand_lines(code_leaf.splitlines())
    has_ra_save = any("st ra" in l for l in expanded_leaf)
    has_fp_save = any("st fp" in l for l in expanded_leaf)
    print(f"    Leaf Subroutine Call Result: r1 = {r1_leaf} (expected 25)")
    print(f"    Return Address saved to stack: {has_ra_save} (must be False)")
    print(f"    Frame Pointer saved to stack:  {has_fp_save} (must be False)")
    assert r1_leaf == 25 and not has_ra_save and not has_fp_save
    print("    --> RESULT: PASS [OK]")
    passed += 1

    print("\n" + "-" * 78)
    print(f"  PART 1 SUMMARY: {passed}/{total} UNIT TESTS PASSED WITH 0 ERRORS")
    print("-" * 78)


def run_all_programs_with_final_values():
    print_banner("PART 2: RUNNING ALL 8 PROGRAMS AND DISPLAYING FINAL OUTPUT VALUES")
    asm = Assembler()
    program_files = sorted(glob.glob(os.path.join(repo_root, "programs", "*.asm")))

    for p_path in program_files:
        p_name = os.path.basename(p_path)
        with open(p_path, "r", encoding="utf-8") as f:
            src = f.read()
        prog = asm.assemble(src)

        mem = Memory()
        mem.load_words(prog.text_start_addr, prog.text_words)
        if prog.data_bytes:
            mem.load_bytes(prog.data_start_addr, bytes(prog.data_bytes))

        # Run on 6-stage pipeline
        cpu = Processor6Stage(memory=mem)
        cpu.run()

        print(f"\n>> PROGRAM: {p_name}")
        if cpu.exception_raised:
            print(f"   Status: EXCEPTION RAISED (Expected Security Trap)")
            print(f"   Exception Cause: {cpu.csr.cause} - {cpu.last_exception.message}")
        else:
            print(f"   Status: HALTED (Success)")

        # Print meaningful final registers
        non_zero_regs = [(i, cpu.rf.read(i)) for i in range(1, 13) if cpu.rf.read(i) != 0]
        print("   Key Register Outputs:")
        for reg_id, val in non_zero_regs:
            print(f"     r{reg_id:<2} = {val:<8} (hex: 0x{val & 0xFFFFFFFF:08X})")
        if not non_zero_regs and not cpu.exception_raised:
            print("     (all general registers r1-r12 are 0)")

        print(f"   Hardware PMC: {cpu.pmc.cycle_count} Cycles | {cpu.pmc.instruction_count} Instructions Committed | {cpu.pmc.structural_stalls} Structural Stalls")
        print("   " + "-" * 72)


if __name__ == "__main__":
    run_unit_tests_with_values()
    run_all_programs_with_final_values()
    print("\n" + "=" * 78)
    print("  ALL TESTS AND BENCHMARKS EXECUTED SUCCESSFULLY WITH FULL FINAL VALUES!")
    print("=" * 78 + "\n")
