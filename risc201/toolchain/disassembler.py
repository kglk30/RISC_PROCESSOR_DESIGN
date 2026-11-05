"""
RISC201 Disassembler
Parses 32-bit binary or hexadecimal word representations and reconstructs
human-readable RISC201 assembly instructions.
"""

from typing import List, Optional
from risc201.core.isa import (
    Opcode, DecodedInstruction, decode_instruction, REGISTER_NAMES,
    is_branch_op, is_memory_op, to_unsigned32
)

class Disassembler:
    """
    Reconstructs assembly syntax from 32-bit machine code words.
    """
    @staticmethod
    def reg_name(reg_idx: int) -> str:
        if reg_idx == 0:
            return "r0"
        if reg_idx == 13:
            return "fp"
        if reg_idx == 14:
            return "sp"
        if reg_idx == 15:
            return "ra"
        return f"r{reg_idx}"

    @classmethod
    def disassemble_word(cls, word: int, current_pc: int = 0) -> str:
        inst = decode_instruction(word)
        op = inst.opcode

        if op == Opcode.NOP:
            return "nop"
        if op == Opcode.HLT:
            return "hlt"
        if op == Opcode.RET:
            return "ret"
        if op == Opcode.TRAP:
            return f"trap {inst.trap_id}"

        # Branches
        if is_branch_op(op):
            target_pc = current_pc + (inst.offset * 4)
            return f"{inst.op_name} 0x{target_pc:04X}  ; offset={inst.offset}"

        # Memory
        if is_memory_op(op):
            rd = cls.reg_name(inst.rd)
            rs1 = cls.reg_name(inst.rs1)
            return f"{inst.op_name} {rd}, {inst.imm}[{rs1}]"

        # MOV
        if op == Opcode.MOV:
            rd = cls.reg_name(inst.rd)
            if inst.is_imm:
                return f"mov {rd}, {inst.imm}"
            else:
                rs1 = cls.reg_name(inst.rs1)
                return f"mov {rd}, {rs1}"

        # NOT
        if op == Opcode.NOT:
            rd = cls.reg_name(inst.rd)
            rs1 = cls.reg_name(inst.rs1)
            return f"not {rd}, {rs1}"

        # CLZ / POPCNT (unary: rd, rs1)
        if op in (Opcode.CLZ, Opcode.POPCNT):
            rd = cls.reg_name(inst.rd)
            rs1 = cls.reg_name(inst.rs1)
            return f"{inst.op_name} {rd}, {rs1}"

        # CMP
        if op == Opcode.CMP:
            rs1 = cls.reg_name(inst.rs1)
            if inst.is_imm:
                return f"cmp {rs1}, {inst.imm}"
            else:
                rs2 = cls.reg_name(inst.rs2)
                return f"cmp {rs1}, {rs2}"

        # Standard ALU 3-operand
        rd = cls.reg_name(inst.rd)
        rs1 = cls.reg_name(inst.rs1)
        if inst.is_imm:
            return f"{inst.op_name} {rd}, {rs1}, {inst.imm}"
        else:
            rs2 = cls.reg_name(inst.rs2)
            return f"{inst.op_name} {rd}, {rs1}, {rs2}"

    @classmethod
    def disassemble_hex(cls, hex_str: str, current_pc: int = 0) -> str:
        word = int(hex_str.strip(), 16)
        return cls.disassemble_word(word, current_pc)

    @classmethod
    def disassemble_binary(cls, bin_str: str, current_pc: int = 0) -> str:
        cleaned = bin_str.replace(" ", "").strip()
        word = int(cleaned, 2)
        return cls.disassemble_word(word, current_pc)

    @classmethod
    def disassemble_words(cls, words: List[int], start_pc: int = 0) -> List[str]:
        out = []
        for i, word in enumerate(words):
            pc = start_pc + (i * 4)
            u32 = to_unsigned32(word)
            asm_line = cls.disassemble_word(word, pc)
            out.append(f"0x{pc:08X}: 0x{u32:08X}    {asm_line}")
        return out
