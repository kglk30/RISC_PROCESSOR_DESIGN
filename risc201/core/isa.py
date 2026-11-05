"""
RISC201 Instruction Set Architecture & Specification
Based on Prof. Smruti R. Sarangi's SimpleRisc with modern extensions.
"""

from enum import IntEnum
from typing import Dict, Optional, Tuple

class Opcode(IntEnum):
    ADD    = 0   # 00000
    SUB    = 1   # 00001
    MUL    = 2   # 00010
    DIV    = 3   # 00011
    MOD    = 4   # 00100
    CMP    = 5   # 00101
    AND    = 6   # 00110
    OR     = 7   # 00111
    NOT    = 8   # 01000
    MOV    = 9   # 01001
    LSL    = 10  # 01010
    LSR    = 11  # 01011
    ASR    = 12  # 01100
    NOP    = 13  # 01101
    LD     = 14  # 01110
    ST     = 15  # 01111
    BEQ    = 16  # 10000
    BGT    = 17  # 10001
    B      = 18  # 10010
    CALL   = 19  # 10011
    RET    = 20  # 10100
    BLT    = 21  # 10101
    BNE    = 22  # 10110
    TRAP   = 23  # 10111 - Software interrupt / trap / canary check
    CLZ    = 24  # 11000 - Count Leading Zeros
    POPCNT = 25  # 11001 - Population Count (Hamming weight)
    HLT    = 31  # 11111 - Halt execution

OPCODE_NAMES: Dict[int, str] = {op.value: op.name.lower() for op in Opcode}
NAME_TO_OPCODE: Dict[str, Opcode] = {op.name.lower(): op for op in Opcode}

# Register aliases
REGISTER_ALIASES: Dict[str, int] = {
    f"r{i}": i for i in range(16)
}
REGISTER_ALIASES.update({
    "zero": 0,
    "fp": 13,
    "sp": 14,
    "ra": 15,
    "lr": 15,
})

REGISTER_NAMES: Dict[int, str] = {i: f"r{i}" for i in range(16)}
REGISTER_NAMES[0] = "r0(zero)"
REGISTER_NAMES[13] = "r13(fp)"
REGISTER_NAMES[14] = "r14(sp)"
REGISTER_NAMES[15] = "r15(ra)"

# Instruction Format Enum
class FormatType(IntEnum):
    REGISTER = 0
    IMMEDIATE = 1
    BRANCH = 2
    TRAP = 3

def is_branch_op(op_or_inst) -> bool:
    op = op_or_inst.opcode if hasattr(op_or_inst, "opcode") else op_or_inst
    return op in (Opcode.BEQ, Opcode.BGT, Opcode.B, Opcode.CALL, Opcode.RET, Opcode.BLT, Opcode.BNE)

def is_memory_op(op_or_inst) -> bool:
    op = op_or_inst.opcode if hasattr(op_or_inst, "opcode") else op_or_inst
    return op in (Opcode.LD, Opcode.ST)

def is_alu_op(op_or_inst) -> bool:
    op = op_or_inst.opcode if hasattr(op_or_inst, "opcode") else op_or_inst
    return op in (
        Opcode.ADD, Opcode.SUB, Opcode.MUL, Opcode.DIV, Opcode.MOD,
        Opcode.CMP, Opcode.AND, Opcode.OR, Opcode.NOT, Opcode.MOV,
        Opcode.LSL, Opcode.LSR, Opcode.ASR, Opcode.CLZ, Opcode.POPCNT
    )

def is_multi_cycle_op(op_or_inst) -> bool:
    """Returns True if this operation has > 1 ALU latency cycle (for stall insertion)."""
    op = op_or_inst.opcode if hasattr(op_or_inst, "opcode") else op_or_inst
    return op in (Opcode.MUL, Opcode.DIV, Opcode.MOD)

def sign_extend(val: int, bits: int) -> int:
    """Sign-extend an integer of given bit width to 32-bit signed."""
    val = val & ((1 << bits) - 1)
    if val & (1 << (bits - 1)):
        return val - (1 << bits)
    return val

def to_unsigned32(val: int) -> int:
    """Convert integer to 32-bit unsigned representation."""
    return val & 0xFFFFFFFF

def to_signed32(val: int) -> int:
    """Convert integer to 32-bit signed representation."""
    val = val & 0xFFFFFFFF
    if val & 0x80000000:
        return val - 0x100000000
    return val

class DecodedInstruction:
    """Represents an unpacked RISC201 instruction."""
    def __init__(
        self,
        raw: int,
        opcode: int,
        is_imm: bool = False,
        rd: int = 0,
        rs1: int = 0,
        rs2: int = 0,
        imm: int = 0,
        offset: int = 0,
        trap_id: int = 0
    ):
        self.raw = raw
        self.opcode = opcode
        self.is_imm = is_imm
        self.rd = rd
        self.rs1 = rs1
        self.rs2 = rs2
        self.imm = imm
        self.offset = offset
        self.trap_id = trap_id

    @property
    def op_name(self) -> str:
        return OPCODE_NAMES.get(self.opcode, f"unk_{self.opcode}")

    @property
    def writes_rf(self) -> bool:
        """Whether this instruction writes to the register file."""
        if self.opcode in (Opcode.CMP, Opcode.ST, Opcode.NOP, Opcode.BEQ,
                           Opcode.BGT, Opcode.B, Opcode.RET, Opcode.BLT,
                           Opcode.BNE, Opcode.TRAP, Opcode.HLT):
            return False
        # Call writes return address to r15
        if self.opcode == Opcode.CALL:
            return True
        # For rd == 0, write is ignored by hardwired zero, but architecturally it's a target
        return True

    @property
    def dest_reg(self) -> int:
        if self.opcode == Opcode.CALL:
            return 15  # ra
        return self.rd

    @property
    def reads_rs1(self) -> bool:
        if self.opcode in (Opcode.NOP, Opcode.B, Opcode.CALL, Opcode.RET, Opcode.TRAP, Opcode.HLT):
            return False
        if self.opcode == Opcode.MOV and self.is_imm:
            return False
        return True

    @property
    def reads_rs2(self) -> bool:
        if self.is_imm:
            # Note: For ST, rd is the source of the value being stored!
            # st rd, imm[rs1] -> reads rd and rs1
            return False
        if self.opcode == Opcode.ST:
            return True
        if self.opcode in (Opcode.NOT, Opcode.MOV, Opcode.NOP, Opcode.LD,
                           Opcode.BEQ, Opcode.BGT, Opcode.B, Opcode.CALL,
                           Opcode.RET, Opcode.BLT, Opcode.BNE, Opcode.TRAP, Opcode.HLT,
                           Opcode.CLZ, Opcode.POPCNT):
            return False
        return True

    def __repr__(self) -> str:
        return f"DecodedInstruction({self.op_name}, rd=r{self.rd}, rs1=r{self.rs1}, rs2=r{self.rs2}, imm={self.imm}, offset={self.offset})"


def decode_instruction(word: int) -> DecodedInstruction:
    """Decodes a 32-bit machine word into a DecodedInstruction."""
    word = to_unsigned32(word)
    op = (word >> 27) & 0x1F

    if op == Opcode.TRAP:
        trap_id = word & 0x07FFFFFF
        return DecodedInstruction(raw=word, opcode=op, trap_id=trap_id)

    if op == Opcode.HLT or op == Opcode.NOP:
        return DecodedInstruction(raw=word, opcode=op)

    if is_branch_op(op):
        if op == Opcode.RET:
            return DecodedInstruction(raw=word, opcode=op)
        offset = sign_extend(word & 0x07FFFFFF, 27)
        return DecodedInstruction(raw=word, opcode=op, offset=offset)

    is_imm = bool((word >> 26) & 0x01)
    rd = (word >> 22) & 0x0F
    rs1 = (word >> 18) & 0x0F

    if is_imm:
        imm = sign_extend(word & 0x3FFFF, 18)
        return DecodedInstruction(
            raw=word, opcode=op, is_imm=True, rd=rd, rs1=rs1, imm=imm
        )
    else:
        rs2 = (word >> 14) & 0x0F
        return DecodedInstruction(
            raw=word, opcode=op, is_imm=False, rd=rd, rs1=rs1, rs2=rs2
        )


def encode_instruction(inst: DecodedInstruction) -> int:
    """Encodes a DecodedInstruction into a 32-bit machine word."""
    op = inst.opcode & 0x1F

    if op == Opcode.TRAP:
        return (op << 27) | (inst.trap_id & 0x07FFFFFF)

    if op in (Opcode.NOP, Opcode.HLT, Opcode.RET):
        return (op << 27)

    if is_branch_op(op):
        offset = inst.offset & 0x07FFFFFF
        return (op << 27) | offset

    is_imm_bit = 1 if inst.is_imm else 0
    rd = inst.rd & 0x0F
    rs1 = inst.rs1 & 0x0F

    if inst.is_imm:
        imm = inst.imm & 0x3FFFF
        return (op << 27) | (is_imm_bit << 26) | (rd << 22) | (rs1 << 18) | imm
    else:
        rs2 = inst.rs2 & 0x0F
        return (op << 27) | (is_imm_bit << 26) | (rd << 22) | (rs1 << 18) | (rs2 << 14)
