"""
Comprehensive Test Suite for RISC201 Simulation Environment
Tests:
- Hardwired r0
- ALU Operations and Algorithms (Booth, Restoring, flags)
- Memory boundaries, alignment, and Red Zone guard page
- Stack Preprocessor macros and Stack Canary verification
- Assembler and Disassembler round-trips
- 4-Stage and 6-Stage Pipeline execution
- Microprogrammed CPU execution
- CSR Exception Trapping
"""

import os
import sys
import unittest
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from risc201.core.isa import (
    Opcode, DecodedInstruction, decode_instruction, encode_instruction,
    to_signed32, to_unsigned32
)
from risc201.core.registers import RegisterFile, CSRFile, CSRCause, CPUException
from risc201.alu.alu import ALU, MultiplierAlgorithm, DividerAlgorithm, DivisionByZeroException
from risc201.core.memory import Memory
from risc201.core.stack import StackPreprocessor, CANARY_MAGIC
from risc201.toolchain.assembler import Assembler
from risc201.toolchain.disassembler import Disassembler
from risc201.pipelines.pipeline_4stage import Processor4Stage
from risc201.pipelines.pipeline_6stage import Processor6Stage
from risc201.control.microcode import MicroprogrammedCPU

class TestRISC201(unittest.TestCase):

    def test_hardwired_r0(self):
        rf = RegisterFile()
        rf.reset()
        # Verify initial read is 0
        self.assertEqual(rf.read(0), 0)

        # Attempt writes to r0
        rf.write(0, 100)
        self.assertEqual(rf.read(0), 0, "r0 must ignore writes")
        rf.write(0, -9999)
        self.assertEqual(rf.read(0), 0, "r0 must remain 0")

        # Other registers work normally
        rf.write(1, 42)
        self.assertEqual(rf.read(1), 42)

    def test_alu_operations(self):
        alu = ALU()
        # ADD
        res = alu.execute(Opcode.ADD, 15, 25)
        self.assertEqual(res, 40)
        self.assertFalse(alu.flags.Z)
        self.assertFalse(alu.flags.N)

        # SUB and Zero flag
        res = alu.execute(Opcode.SUB, 25, 25)
        self.assertEqual(res, 0)
        self.assertTrue(alu.flags.Z)

        # Negative flag
        res = alu.execute(Opcode.SUB, 10, 20)
        self.assertEqual(res, -10)
        self.assertTrue(alu.flags.N)

        # MUL fast
        res = alu.execute(Opcode.MUL, 6, 7)
        self.assertEqual(res, 42)

        # MUL Booth's algorithm
        alu_booth = ALU(mul_algo=MultiplierAlgorithm.BOOTH)
        res = alu_booth.execute(Opcode.MUL, 12, -4)
        self.assertEqual(res, -48)

        # DIV and Restoring Division
        alu_div = ALU(div_algo=DividerAlgorithm.RESTORING)
        res = alu_div.execute(Opcode.DIV, 100, 4)
        self.assertEqual(res, 25)

        # Division by zero
        with self.assertRaises(DivisionByZeroException):
            alu.execute(Opcode.DIV, 10, 0)

        # Logic & Shifts
        self.assertEqual(alu.execute(Opcode.AND, 0b1100, 0b1010), 0b1000)
        self.assertEqual(alu.execute(Opcode.OR, 0b1100, 0b1010), 0b1110)
        self.assertEqual(alu.execute(Opcode.LSL, 5, 2), 20)
        self.assertEqual(alu.execute(Opcode.ASR, -16, 2), -4)

    def test_dadda_multiplier(self):
        """Dadda tree multiplier correctness tests."""
        alu = ALU(mul_algo=MultiplierAlgorithm.DADDA)

        # Positive × Positive
        self.assertEqual(alu.execute(Opcode.MUL, 7, 8), 56)
        self.assertEqual(alu.execute(Opcode.MUL, 100, 100), 10000)
        self.assertEqual(alu.execute(Opcode.MUL, 1, 0), 0)
        self.assertTrue(alu.flags.Z)

        # Negative × Positive
        self.assertEqual(alu.execute(Opcode.MUL, -3, 4), -12)
        self.assertTrue(alu.flags.N)

        # Negative × Negative
        self.assertEqual(alu.execute(Opcode.MUL, -5, -6), 30)

        # Large values (lower 32 bits)
        self.assertEqual(alu.execute(Opcode.MUL, 65536, 65536), 0)  # 2^32 → wraps

        # Cross-check: Dadda must match Booth for same inputs
        alu_booth = ALU(mul_algo=MultiplierAlgorithm.BOOTH)
        for a, b in [(12, 34), (-7, 11), (0, 999), (-128, -128), (2**15, 2**15)]:
            dadda_res = alu.execute(Opcode.MUL, a, b)
            booth_res = alu_booth.execute(Opcode.MUL, a, b)
            self.assertEqual(dadda_res, booth_res,
                             f"Dadda vs Booth mismatch: {a}*{b} → {dadda_res} vs {booth_res}")

    def test_srt_division(self):
        """SRT radix-2 division correctness tests."""
        alu = ALU(div_algo=DividerAlgorithm.SRT)

        # Basic positive division
        self.assertEqual(alu.execute(Opcode.DIV, 20, 4), 5)
        self.assertEqual(alu.execute(Opcode.DIV, 17, 3), 5)   # truncate toward zero
        self.assertEqual(alu.execute(Opcode.MOD, 17, 3), 2)

        # Negative dividend
        self.assertEqual(alu.execute(Opcode.DIV, -20, 4), -5)
        self.assertEqual(alu.execute(Opcode.DIV, -17, 3), -5)
        self.assertEqual(alu.execute(Opcode.MOD, -17, 3), -2)

        # Negative divisor
        self.assertEqual(alu.execute(Opcode.DIV, 20, -4), -5)
        self.assertEqual(alu.execute(Opcode.MOD, 20, -4), 0)

        # Both negative
        self.assertEqual(alu.execute(Opcode.DIV, -20, -4), 5)

        # Division by one
        self.assertEqual(alu.execute(Opcode.DIV, 42, 1), 42)

        # Zero dividend
        self.assertEqual(alu.execute(Opcode.DIV, 0, 7), 0)
        self.assertTrue(alu.flags.Z)

        # Division by zero
        with self.assertRaises(DivisionByZeroException):
            alu.execute(Opcode.DIV, 10, 0)

        # Cross-check SRT against restoring for positive values
        alu_res = ALU(div_algo=DividerAlgorithm.RESTORING)
        for dvd, dvs in [(100, 7), (255, 16), (1000, 31), (1, 1), (31, 32)]:
            srt_q = alu.execute(Opcode.DIV, dvd, dvs)
            res_q = alu_res.execute(Opcode.DIV, dvd, dvs)
            self.assertEqual(srt_q, res_q,
                             f"SRT vs Restoring DIV mismatch: {dvd}/{dvs} → {srt_q} vs {res_q}")

    def test_clz(self):
        """Count Leading Zeros (CLZ) correctness tests."""
        alu = ALU()

        # All zeros
        self.assertEqual(alu.execute(Opcode.CLZ, 0, 0), 32)

        # MSB set
        self.assertEqual(alu.execute(Opcode.CLZ, 0x80000000, 0), 0)

        # Single bit at various positions
        self.assertEqual(alu.execute(Opcode.CLZ, 1, 0), 31)       # bit 0 set
        self.assertEqual(alu.execute(Opcode.CLZ, 2, 0), 30)       # bit 1 set
        self.assertEqual(alu.execute(Opcode.CLZ, 0x40000000, 0), 1)  # bit 30 set

        # Some common values
        self.assertEqual(alu.execute(Opcode.CLZ, 0xFF, 0), 24)
        self.assertEqual(alu.execute(Opcode.CLZ, 0xFFFF, 0), 16)
        self.assertEqual(alu.execute(Opcode.CLZ, 0x0001_0000, 0), 15)

        # Result is non-negative
        self.assertFalse(alu.flags.N)

    def test_popcnt_hamming(self):
        """Population Count (POPCNT / Hamming weight) correctness tests."""
        alu = ALU()

        self.assertEqual(alu.execute(Opcode.POPCNT, 0, 0), 0)
        self.assertTrue(alu.flags.Z)

        self.assertEqual(alu.execute(Opcode.POPCNT, 0xFFFFFFFF, 0), 32)
        self.assertEqual(alu.execute(Opcode.POPCNT, 1, 0), 1)
        self.assertEqual(alu.execute(Opcode.POPCNT, 0b1010_1010_1010_1010_1010_1010_1010_1010, 0), 16)
        self.assertEqual(alu.execute(Opcode.POPCNT, 0x5555_5555, 0), 16)
        self.assertEqual(alu.execute(Opcode.POPCNT, 0x8000_0001, 0), 2)

        # Cross-check against Python's bin().count('1') reference
        import random
        rng = random.Random(42)
        for _ in range(50):
            val = rng.randint(0, 0xFFFFFFFF)
            expected = bin(val).count('1')
            got = alu.execute(Opcode.POPCNT, val, 0)
            self.assertEqual(got, expected, f"POPCNT({val:#010x}) expected {expected} got {got}")

    def test_memory_safety(self):
        mem = Memory(size=0x10000)
        mem.write_word(0x1000, 0x12345678)
        self.assertEqual(mem.read_word(0x1000), 0x12345678)

        # Misalignment check
        with self.assertRaises(CPUException) as cm:
            mem.read_word(0x1001)
        self.assertEqual(cm.exception.cause, CSRCause.MISALIGNED_ACCESS)

        # Red Zone guard check
        with self.assertRaises(CPUException) as cm:
            mem.write_word(0x00002F00, 0xCAFEBABE)
        self.assertEqual(cm.exception.cause, CSRCause.STACK_OVERFLOW)

    def test_assembler_disassembler(self):
        asm_code = """
        .text
        main:
            add r1, r2, r3
            ld r4, 16[r5]
            st r6, 0[sp]
            beq target
            nop
        target:
            hlt
        """
        assembler = Assembler()
        prog = assembler.assemble(asm_code)
        self.assertEqual(len(prog.text_words), 6)

        # Disassemble instructions
        dis0 = Disassembler.disassemble_word(prog.text_words[0], 0x00)
        self.assertEqual(dis0, "add r1, r2, r3")

        dis1 = Disassembler.disassemble_word(prog.text_words[1], 0x04)
        self.assertEqual(dis1, "ld r4, 16[r5]")

        dis2 = Disassembler.disassemble_word(prog.text_words[2], 0x08)
        self.assertEqual(dis2, "st r6, 0[sp]")

    def test_pipeline_4stage_execution(self):
        code = """
        .text
        mov r1, 10
        mov r2, 20
        add r3, r1, r2
        sub r4, r3, 5
        hlt
        """
        assembler = Assembler()
        prog = assembler.assemble(code)

        mem = Memory()
        mem.load_words(prog.text_start_addr, prog.text_words)
        cpu = Processor4Stage(memory=mem)
        cpu.run()

        self.assertTrue(cpu.halted)
        self.assertEqual(cpu.rf.read(1), 10)
        self.assertEqual(cpu.rf.read(2), 20)
        self.assertEqual(cpu.rf.read(3), 30)
        self.assertEqual(cpu.rf.read(4), 25)

    def test_pipeline_6stage_execution(self):
        code = """
        .text
        mov r1, 7
        mov r2, 8
        mul r3, r1, r2
        add r4, r3, r0
        hlt
        """
        assembler = Assembler()
        prog = assembler.assemble(code)

        mem = Memory()
        mem.load_words(prog.text_start_addr, prog.text_words)
        cpu = Processor6Stage(memory=mem)
        cpu.run()

        self.assertTrue(cpu.halted)
        self.assertEqual(cpu.rf.read(3), 56)
        self.assertEqual(cpu.rf.read(4), 56)

    def test_microcode_execution(self):
        code = """
        .text
        mov r1, 15
        mov r2, 3
        div r3, r1, r2
        mod r4, r1, r2
        hlt
        """
        assembler = Assembler()
        prog = assembler.assemble(code)

        # Test horizontal
        mem_h = Memory()
        mem_h.load_words(prog.text_start_addr, prog.text_words)
        cpu_h = MicroprogrammedCPU(memory=mem_h, use_vertical=False)
        cpu_h.run()
        self.assertEqual(cpu_h.rf.read(3), 5)
        self.assertEqual(cpu_h.rf.read(4), 0)

        # Test vertical
        mem_v = Memory()
        mem_v.load_words(prog.text_start_addr, prog.text_words)
        cpu_v = MicroprogrammedCPU(memory=mem_v, use_vertical=True)
        cpu_v.run()
        self.assertEqual(cpu_v.rf.read(3), 5)
        self.assertEqual(cpu_v.rf.read(4), 0)

    def test_stack_canary_protection(self):
        code = """
        .text
        main:
            call test_vuln
            hlt
        test_vuln:
            enter 4
            ; Smash the canary at 4[sp]
            mov r2, 0x11223344
            st r2, 4[sp]
            leave 4
        """
        assembler = Assembler()
        prog = assembler.assemble(code)

        mem = Memory()
        mem.load_words(prog.text_start_addr, prog.text_words)
        cpu = Processor4Stage(memory=mem)
        cpu.run()

        self.assertTrue(cpu.exception_raised)
        self.assertEqual(cpu.csr.cause, CSRCause.STACK_CANARY_CORRUPTED)


    def test_stack_preprocessor_same_line_labels(self):
        """Regression: label + instruction on one line used to raise NameError."""
        sp = StackPreprocessor()
        out = sp.expand_lines(["main: mov r1, 10"])
        self.assertEqual(len(out), 1)
        self.assertTrue(out[0].startswith("main:"))
        self.assertIn("mov r1, 10", out[0])

    def test_leaf_function_optimization(self):
        """
        Leaf function optimization:
        Avoids saving the return address and frame pointer when safe.
        """
        sp = StackPreprocessor()
        # 1. Verify enter_leaf / leave_leaf omit ra and fp
        lines = [
            "my_leaf: enter_leaf 0",
            "add r1, r1, 5",
            "leave_leaf 0"
        ]
        expanded = sp.expand_lines(lines)
        expanded_str = "\n".join(expanded)
        self.assertNotIn("st ra, 0[sp]", expanded_str)
        self.assertNotIn("st fp, 0[sp]", expanded_str)
        self.assertNotIn("ld fp, 0[sp]", expanded_str)
        self.assertNotIn("ld ra, 0[sp]", expanded_str)
        self.assertIn("ret", expanded_str)

        # 2. Verify with local variable allocation
        lines_local = [
            "leaf_local: enter_leaf 8",
            "st r1, 0[sp]",
            "leave_leaf 8"
        ]
        expanded_local = sp.expand_lines(lines_local)
        exp_loc_str = "\n".join(expanded_local)
        self.assertIn("sub sp, sp, 8", exp_loc_str)
        self.assertIn("add sp, sp, 8", exp_loc_str)
        self.assertNotIn("st ra", exp_loc_str)

        # 3. Execution test on 4-stage and 6-stage pipelines
        code = """
        .text
        .globl main
        main:
            mov r1, 15
            call leaf_add
            ; r1 should now be 25 (15 + 10)
            hlt

        leaf_add:
            enter_leaf 0
            add r1, r1, 10
            leave_leaf 0
        """
        asm = Assembler()
        prog = asm.assemble(code)

        # Run on 4-stage
        mem4 = Memory()
        mem4.load_words(prog.text_start_addr, prog.text_words)
        cpu4 = Processor4Stage(memory=mem4)
        cpu4.run()
        self.assertEqual(cpu4.rf.read(1), 25)

        # Run on 6-stage
        mem6 = Memory()
        mem6.load_words(prog.text_start_addr, prog.text_words)
        cpu6 = Processor6Stage(memory=mem6)
        cpu6.run()
        self.assertEqual(cpu6.rf.read(1), 25)

        # 4. Automatic leaf detection when optimize_leaf=True
        sp_auto = StackPreprocessor(optimize_leaf=True)
        code_auto = [
            "auto_leaf: enter 0",
            "mov r2, 42",
            "leave 0"
        ]
        exp_auto = "\n".join(sp_auto.expand_lines(code_auto))
        self.assertNotIn("st ra, 0[sp]", exp_auto)
        self.assertNotIn("st fp, 0[sp]", exp_auto)


    def test_microcode_matches_pipeline_on_branches_calls_and_traps(self):
        """Regression: micro CPU lacked BNE/BGT/BLT/TRAP and double-executed CALL/LD."""
        import glob
        asm = Assembler()
        for path in sorted(glob.glob(os.path.join(os.path.dirname(__file__), "..", "programs", "*.asm"))):
            with open(path, "r", encoding="utf-8") as f:
                prog = asm.assemble(f.read())
            states = []
            for cls, kw in ((Processor4Stage, {}),
                            (MicroprogrammedCPU, {"use_vertical": False}),
                            (MicroprogrammedCPU, {"use_vertical": True})):
                mem = Memory()
                mem.load_words(prog.text_start_addr, prog.text_words)
                if prog.data_bytes:
                    mem.load_bytes(prog.data_start_addr, bytes(prog.data_bytes))
                cpu = cls(memory=mem, **kw)
                cpu.run()
                states.append(([cpu.rf.read(i) for i in range(16)], cpu.exception_raised))
            self.assertEqual(states[0], states[1], path)
            self.assertEqual(states[0], states[2], path)


if __name__ == "__main__":
    unittest.main()
