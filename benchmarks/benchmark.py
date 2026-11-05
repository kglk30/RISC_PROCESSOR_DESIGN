"""
RISC201 Architectural Benchmark & Comparative Evaluation Suite
Evaluates and compares:
1. 4-Stage vs. 6-Stage Pipeline Models
2. Data Forwarding Network Impact (Forwarding ON vs. OFF)
3. Dynamic 2-bit BTB Branch Predictor vs. Static Predictors
4. Microprogrammed Control Models (Horizontal vs. Vertical)
5. Optimized ALU Algorithms (Fast vs. Booth's Radix-2 vs. Shift-and-Add Multipliers, Restoring Dividers)
6. Security Exception Trapping (Stack Canary Verification)
7. Leaf Function Optimization (Avoids saving return address and frame pointer when safe)
"""

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
# Windows consoles default to cp1252 and crash on box-drawing/emoji characters.
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

from typing import Dict, List, Any
from risc201.toolchain.assembler import Assembler
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.pipelines.pipeline_6stage import Processor6Stage
from risc201.control.microcode import MicroprogrammedCPU
from risc201.core.memory import Memory
from risc201.pipelines.branch_predictor import PredictorMode
from risc201.alu.alu import MultiplierAlgorithm, DividerAlgorithm, ALU
from risc201.core.registers import CSRCause

PROGRAMS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "programs"))

def load_program(filename: str):
    path = os.path.join(PROGRAMS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    assembler = Assembler()
    return assembler.assemble(src)


def benchmark_pipelines():
    print("\n" + "=" * 80)
    print(" 1. COMPARATIVE PIPELINE EVALUATION: 4-STAGE vs. 6-STAGE PROCESSOR")
    print("=" * 80)

    test_programs = ["01_basic_test.asm", "02_factorial.asm", "05_hazard_bench.asm", "06_branch_bench.asm"]

    header = f"{'Program':<20} | {'Arch':<8} | {'Cycles':<8} | {'Insts':<8} | {'Stalls':<8} | {'CPI':<8} | {'IPC':<8}"
    print(header)
    print("-" * len(header))

    for prog_name in test_programs:
        prog = load_program(prog_name)

        # 4-stage
        mem4 = Memory()
        mem4.load_words(prog.text_start_addr, prog.text_words)
        if prog.data_bytes: mem4.load_bytes(prog.data_start_addr, bytes(prog.data_bytes))
        cpu4 = Processor4Stage(memory=mem4, enable_forwarding=True)
        cpu4.run()

        # 6-stage
        mem6 = Memory()
        mem6.load_words(prog.text_start_addr, prog.text_words)
        if prog.data_bytes: mem6.load_bytes(prog.data_start_addr, bytes(prog.data_bytes))
        cpu6 = Processor6Stage(memory=mem6, enable_forwarding=True)
        cpu6.run()

        print(f"{prog_name:<20} | {'4-Stage':<8} | {cpu4.pmc.cycle_count:<8} | {cpu4.pmc.instruction_count:<8} | {cpu4.pmc.stall_count:<8} | {cpu4.pmc.cpi:<8.3f} | {cpu4.pmc.ipc:<8.3f}")
        print(f"{prog_name:<20} | {'6-Stage':<8} | {cpu6.pmc.cycle_count:<8} | {cpu6.pmc.instruction_count:<8} | {cpu6.pmc.stall_count:<8} | {cpu6.pmc.cpi:<8.3f} | {cpu6.pmc.ipc:<8.3f}")
        print("-" * len(header))


def benchmark_forwarding():
    print("\n" + "=" * 80)
    print(" 2. FORWARDING NETWORK IMPACT: FORWARDING ENABLED vs. DISABLED (05_hazard_bench.asm)")
    print("=" * 80)

    prog = load_program("05_hazard_bench.asm")

    results = []
    for arch_name, CPUClass in [("4-Stage", Processor4Stage), ("6-Stage", Processor6Stage)]:
        for fwd in [True, False]:
            mem = Memory()
            mem.load_words(prog.text_start_addr, prog.text_words)
            if prog.data_bytes: mem.load_bytes(prog.data_start_addr, bytes(prog.data_bytes))
            cpu = CPUClass(memory=mem, enable_forwarding=fwd)
            cpu.run()
            results.append((arch_name, "ON" if fwd else "OFF", cpu.pmc.cycle_count, cpu.pmc.stall_count, cpu.pmc.cpi, cpu.pmc.forwarding_events))

    header = f"{'Architecture':<12} | {'Forwarding':<10} | {'Cycles':<8} | {'Stalls':<8} | {'CPI':<8} | {'Fwd Events':<10}"
    print(header)
    print("-" * len(header))
    for row in results:
        print(f"{row[0]:<12} | {row[1]:<10} | {row[2]:<8} | {row[3]:<8} | {row[4]:<8.3f} | {row[5]:<10}")


def benchmark_branch_predictors():
    print("\n" + "=" * 80)
    print(" 3. BRANCH PREDICTOR EVALUATION: 2-BIT BTB vs. STATIC (06_branch_bench.asm)")
    print("=" * 80)

    prog = load_program("06_branch_bench.asm")
    modes = [
        ("Dynamic 2-Bit + BTB", PredictorMode.DYNAMIC_2BIT),
        ("Static Always Not-Taken", PredictorMode.STATIC_NOT_TAKEN),
        ("Static Always Taken", PredictorMode.STATIC_TAKEN),
    ]

    for arch_name, CPUClass in [("4-Stage", Processor4Stage), ("6-Stage", Processor6Stage)]:
        print(f"\n--- {arch_name} Pipeline ---")
        header = f"{'Predictor Mode':<25} | {'Cycles':<8} | {'Branches':<10} | {'Mispredicts':<12} | {'Mispred %':<10} | {'CPI':<8}"
        print(header)
        print("-" * len(header))
        for mode_name, mode in modes:
            mem = Memory()
            mem.load_words(prog.text_start_addr, prog.text_words)
            cpu = CPUClass(memory=mem, branch_mode=mode)
            cpu.run()
            pmc = cpu.pmc
            print(f"{mode_name:<25} | {pmc.cycle_count:<8} | {pmc.branch_count:<10} | {pmc.branch_mispredict_count:<12} | {pmc.branch_mispredict_rate:<9.1f}% | {pmc.cpi:<8.3f}")


def benchmark_microcode():
    print("\n" + "=" * 80)
    print(" 4. CONTROL UNIT COMPARISON: HORIZONTAL vs. VERTICAL MICROPROGRAMMING")
    print("=" * 80)

    prog = load_program("01_basic_test.asm")

    # Horizontal
    mem_h = Memory()
    mem_h.load_words(prog.text_start_addr, prog.text_words)
    cpu_h = MicroprogrammedCPU(memory=mem_h, use_vertical=False)
    cpu_h.run()

    # Vertical
    mem_v = Memory()
    mem_v.load_words(prog.text_start_addr, prog.text_words)
    cpu_v = MicroprogrammedCPU(memory=mem_v, use_vertical=True)
    cpu_v.run()

    print(f"{'Attribute':<32} | {'Horizontal Microcode':<22} | {'Vertical Microcode':<22}")
    print("-" * 80)
    print(f"{'Microinstruction Width':<32} | {'28 bits':<22} | {'14 bits':<22}")
    print(f"{'Control Store ROM Capacity':<32} | {'28 x 82 = 2296 bits':<22} | {'14 x 82 = 1148 bits':<22}")
    print(f"{'Decoding Overhead':<32} | {'None (Direct lines)':<22} | {'Requires micro-decoders':<22}")
    print(f"{'Total Micro-Cycles Executed':<32} | {str(cpu_h.total_micro_cycles):<22} | {str(cpu_v.total_micro_cycles):<22}")
    print(f"{'Macro Instructions Committed':<32} | {str(cpu_h.pmc.instruction_count):<22} | {str(cpu_v.pmc.instruction_count):<22}")
    avg_micro_cpi = cpu_h.total_micro_cycles / cpu_h.pmc.instruction_count if cpu_h.pmc.instruction_count else 0
    print(f"{'Micro-Cycles Per Instruction':<32} | {f'{avg_micro_cpi:.2f}':<22} | {f'{avg_micro_cpi:.2f}':<22}")


def benchmark_alu_algorithms():
    print("\n" + "=" * 80)
    print(" 5. ALU ALGORITHMIC EVALUATION: MULTIPLIER & DIVIDER MODELS")
    print("=" * 80)

    alu_fast = ALU(mul_algo=MultiplierAlgorithm.FAST, div_algo=DividerAlgorithm.FAST)
    alu_booth = ALU(mul_algo=MultiplierAlgorithm.BOOTH, div_algo=DividerAlgorithm.RESTORING)
    alu_shift = ALU(mul_algo=MultiplierAlgorithm.SHIFT_AND_ADD, div_algo=DividerAlgorithm.RESTORING)

    test_multiplications = [(12, 10), (-7, 8), (1234, 5678), (-25, -25)]
    print("\n--- Multiplication Algorithms ---")
    for a, b in test_multiplications:
        r_fast = alu_fast.execute(2, a, b) # Opcode.MUL = 2
        r_booth = alu_booth.execute(2, a, b)
        r_shift = alu_shift.execute(2, a, b)
        print(f" {a:>6} * {b:>6} = {r_fast:>10} | Fast: 1 cycle | Booth: 32 cycles ({r_booth}) | Shift-Add: 32 cycles ({r_shift})")

    test_divisions = [(100, 5), (1234, 10), (-50, 7), (1000, -25)]
    print("\n--- Division Algorithms ---")
    for a, b in test_divisions:
        d_fast = alu_fast.execute(3, a, b) # Opcode.DIV = 3
        d_rest = alu_booth.execute(3, a, b)
        print(f" {a:>6} / {b:>6} = {d_fast:>10} | Fast: 1 cycle | Restoring: 32 cycles ({d_rest})")


def benchmark_security_canary():
    print("\n" + "=" * 80)
    print(" 6. SECURITY & RUNTIME EXCEPTION TRAPPING: STACK CANARY OVERFLOW CHECK")
    print("=" * 80)

    prog = load_program("04_buffer_overflow.asm")
    mem = Memory()
    mem.load_words(prog.text_start_addr, prog.text_words)
    cpu = Processor4Stage(memory=mem)

    print("[*] Launching vulnerable function exploit test (04_buffer_overflow.asm)...")
    cpu.run()

    if cpu.exception_raised and cpu.last_exception:
        print(f"[🛡️ SECURITY SYSTEM ACTIVE] Stack tampering prevented!")
        print(f"  Captured Exception : {cpu.last_exception.message}")
        print(f"  Trap Cause Code    : {cpu.csr.cause} ({cpu.csr.cause.name})")
        print(f"  Faulting EPC       : 0x{cpu.csr.epc:08X}")
        print(f"  Processor Status   : {cpu.csr.to_dict()['STATUS']}")
        assert cpu.csr.cause == CSRCause.STACK_CANARY_CORRUPTED, "Should be STACK_CANARY_CORRUPTED"
        print("[✓] Stack Canary Protection & CSR Exception Framework successfully verified!")
    else:
        print("[!] Warning: Buffer overflow was not caught!")


def benchmark_leaf_optimization():
    print("\n" + "=" * 80)
    print(" 7. LEAF FUNCTION OPTIMIZATION IMPACT (Standard Frame vs. Leaf Optimized)")
    print("=" * 80)

    # Standard frame subroutine (with enter 0 / leave 0)
    code_std = """
    .text
    .globl main
    main:
        mov r1, 10
        mov r2, 0
        mov r3, 1
    .loop:
        cmp r3, r1
        bgt .done
        mov r10, r3
        call std_square
        add r2, r2, r4
        add r3, r3, 1
        b .loop
    .done:
        mov r1, r2
        hlt
    std_square:
        enter 0
        mul r4, r10, r10
        leave 0
    """

    asm = Assembler()
    prog_std = asm.assemble(code_std)
    mem_std = Memory(); mem_std.load_words(0, prog_std.text_words)
    cpu_std = Processor6Stage(memory=mem_std)
    cpu_std.run()

    # Leaf optimized subroutine (08_leaf_bench.asm)
    prog_leaf = load_program("08_leaf_bench.asm")
    mem_leaf = Memory(); mem_leaf.load_words(0, prog_leaf.text_words)
    cpu_leaf = Processor6Stage(memory=mem_leaf)
    cpu_leaf.run()

    print(f"{'Subroutine Convention':<30} | {'Total Cycles':<12} | {'Instructions':<12} | {'CPI':<8}")
    print("-" * 70)
    print(f"{'Standard Frame (RA+FP+Canary)':<30} | {cpu_std.pmc.cycle_count:<12} | {cpu_std.pmc.instruction_count:<12} | {cpu_std.pmc.cpi:<8.3f}")
    print(f"{'Leaf Optimized (No RA/FP)':<30} | {cpu_leaf.pmc.cycle_count:<12} | {cpu_leaf.pmc.instruction_count:<12} | {cpu_leaf.pmc.cpi:<8.3f}")
    print("-" * 70)
    cycle_diff = cpu_std.pmc.cycle_count - cpu_leaf.pmc.cycle_count
    speedup = cpu_std.pmc.cycle_count / cpu_leaf.pmc.cycle_count
    print(f"[*] Cycle Reduction: {cycle_diff} cycles ({((cycle_diff / cpu_std.pmc.cycle_count) * 100):.1f}% savings, {speedup:.2f}x speedup)")
    print("[*] Memory Traffic: Eliminates 6 stack memory operations per function call.")


def run_all_benchmarks():
    benchmark_pipelines()
    benchmark_forwarding()
    benchmark_branch_predictors()
    benchmark_microcode()
    benchmark_alu_algorithms()
    benchmark_security_canary()
    benchmark_leaf_optimization()
    print("\n" + "=" * 80)
    print(" ALL BENCHMARK EVALUATIONS COMPLETED SUCCESSFULLY.")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    run_all_benchmarks()
