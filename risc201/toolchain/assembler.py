"""
Two-Pass Assembler for RISC201
Features:
- Integrated Stack Preprocessor (push/pop/enter/leave with canary support)
- Directives: .text, .data, .word, .space, .asciiz
- Pass 1: Symbol Table generation and macro expansion
- Pass 2: Machine code generation (Binary, Hex representation)
- Source code line mapping for interactive debugger
"""

import re
from typing import Dict, List, Tuple, Optional, NamedTuple
from risc201.core.isa import (
    Opcode, NAME_TO_OPCODE, REGISTER_ALIASES, DecodedInstruction,
    encode_instruction, to_signed32, to_unsigned32
)
from risc201.core.stack import StackPreprocessor

class AssembledProgram:
    def __init__(self):
        self.text_words: List[int] = []         # Machine code words for .text
        self.text_start_addr: int = 0x00000000
        self.data_bytes: bytearray = bytearray()# Initialized bytes for .data
        self.data_start_addr: int = 0x00001000
        self.symbol_table: Dict[str, int] = {}  # Label -> Memory address
        self.source_map: Dict[int, str] = {}    # Address -> Original source line
        self.listing: List[str] = []            # Formatted listing lines

    def to_hex_lines(self) -> List[str]:
        """Returns formatted list of hex address and machine word strings."""
        lines = []
        for i, word in enumerate(self.text_words):
            addr = self.text_start_addr + (i * 4)
            u32 = to_unsigned32(word)
            src = self.source_map.get(addr, "")
            lines.append(f"0x{addr:08X}: 0x{u32:08X}    ; {src}")
        return lines


class Assembler:
    """
    Two-pass Assembler for RISC201 assembly.
    """
    def __init__(self, canary_check: bool = True, optimize_leaf: bool = False):
        self.preprocessor = StackPreprocessor(optimize_leaf=optimize_leaf)
        self.canary_check = canary_check

    def assemble(self, source_text: str) -> AssembledProgram:
        raw_lines = source_text.splitlines()

        # Step 0: Macro expansion (push, pop, enter, leave)
        expanded_lines = self.preprocessor.expand_lines(raw_lines)

        program = AssembledProgram()
        symbol_table: Dict[str, int] = {}

        # -------------------------------------------------------------
        # PASS 1: Identify Sections, Labels, and Measure Sizes
        # -------------------------------------------------------------
        current_section = ".text"
        text_pc = 0x00000000
        data_addr = 0x00001000

        # Intermediate representations for Pass 2: list of (section, addr, line)
        pass1_items: List[Tuple[str, int, str]] = []

        for line in expanded_lines:
            # Strip comments
            comment_idx = min(
                line.find(";") if line.find(";") != -1 else len(line),
                line.find("#") if line.find("#") != -1 else len(line)
            )
            cleaned = line[:comment_idx].strip()
            if not cleaned:
                continue

            # Check section directives
            if cleaned.lower().startswith(".text"):
                current_section = ".text"
                continue
            elif cleaned.lower().startswith(".data"):
                current_section = ".data"
                continue
            elif cleaned.lower().startswith(".globl") or cleaned.lower().startswith(".global"):
                continue

            # Check for label definition
            if ":" in cleaned:
                parts = cleaned.split(":", 1)
                label = parts[0].strip()
                if label:
                    symbol_table[label] = text_pc if current_section == ".text" else data_addr
                cleaned = parts[1].strip()

            if not cleaned:
                continue

            # Record item with current address
            if current_section == ".text":
                pass1_items.append((".text", text_pc, cleaned))
                text_pc += 4
            else: # .data
                pass1_items.append((".data", data_addr, cleaned))
                # Calculate size needed for data directive
                data_size = self._calc_data_size(cleaned)
                data_addr += data_size

        program.symbol_table = symbol_table

        # -------------------------------------------------------------
        # PASS 2: Encode Machine Words and Emit Binary
        # -------------------------------------------------------------
        for section, addr, line in pass1_items:
            if section == ".text":
                machine_word = self._assemble_instruction(line, addr, symbol_table)
                program.text_words.append(machine_word)
                program.source_map[addr] = line
                u32 = to_unsigned32(machine_word)
                program.listing.append(f"0x{addr:08X}: 0x{u32:08X} | {line}")
            else:
                bytes_emitted = self._assemble_data(line, symbol_table)
                program.data_bytes.extend(bytes_emitted)

        return program

    def _calc_data_size(self, line: str) -> int:
        tokens = line.split(None, 1)
        directive = tokens[0].lower()
        args = tokens[1].strip() if len(tokens) > 1 else ""

        if directive == ".word":
            vals = [v.strip() for v in args.split(",") if v.strip()]
            return len(vals) * 4
        elif directive == ".space":
            return int(args, 0)
        elif directive == ".asciiz":
            # Extract string between quotes
            match = re.search(r'"(.*)"', args)
            if match:
                return len(match.group(1)) + 1  # null terminated
            return 1
        return 0

    def _assemble_data(self, line: str, symbol_table: Dict[str, int]) -> bytes:
        tokens = line.split(None, 1)
        directive = tokens[0].lower()
        args = tokens[1].strip() if len(tokens) > 1 else ""
        out = bytearray()

        if directive == ".word":
            vals = [v.strip() for v in args.split(",") if v.strip()]
            for v in vals:
                # Value could be label or integer
                num = symbol_table.get(v, None)
                if num is None:
                    num = int(v, 0)
                u32 = to_unsigned32(num)
                out.extend([u32 & 0xFF, (u32 >> 8) & 0xFF, (u32 >> 16) & 0xFF, (u32 >> 24) & 0xFF])
        elif directive == ".space":
            count = int(args, 0)
            out.extend([0] * count)
        elif directive == ".asciiz":
            match = re.search(r'"(.*)"', args)
            string_val = match.group(1) if match else ""
            raw = string_val.encode("utf-8") + b"\x00"
            out.extend(raw)
        return bytes(out)

    def _parse_reg(self, token: str) -> int:
        token = token.strip().lower()
        if token in REGISTER_ALIASES:
            return REGISTER_ALIASES[token]
        raise ValueError(f"Unknown register name: '{token}'")

    def _parse_int(self, token: str, symbol_table: Dict[str, int]) -> int:
        token = token.strip()
        if token in symbol_table:
            return symbol_table[token]
        return int(token, 0)

    def _assemble_instruction(self, line: str, pc: int, symbol_table: Dict[str, int]) -> int:
        tokens = line.split(None, 1)
        mnemonic = tokens[0].lower()
        arg_str = tokens[1].strip() if len(tokens) > 1 else ""

        # Normalize operands split by comma
        args = [a.strip() for a in arg_str.split(",") if a.strip()]

        if mnemonic not in NAME_TO_OPCODE:
            raise ValueError(f"Unknown instruction mnemonic: '{mnemonic}' at PC 0x{pc:08X}")

        opcode = NAME_TO_OPCODE[mnemonic]

        # 1. Zero-operand instructions
        if opcode in (Opcode.NOP, Opcode.HLT, Opcode.RET):
            return encode_instruction(DecodedInstruction(raw=0, opcode=opcode))

        # 2. Trap instruction
        if opcode == Opcode.TRAP:
            trap_id = self._parse_int(args[0], symbol_table) if args else 0
            return encode_instruction(DecodedInstruction(raw=0, opcode=opcode, trap_id=trap_id))

        # 3. Branch Instructions (offset relative in instructions = (target - pc) / 4)
        if opcode in (Opcode.BEQ, Opcode.BGT, Opcode.B, Opcode.CALL, Opcode.BLT, Opcode.BNE):
            target_token = args[0]
            if target_token in symbol_table:
                target_addr = symbol_table[target_token]
                offset = (target_addr - pc) // 4
            else:
                offset = int(target_token, 0)
            return encode_instruction(DecodedInstruction(raw=0, opcode=opcode, offset=offset))

        # 4. Memory Instructions: ld rd, imm[rs1] or st rd, imm[rs1]
        if opcode in (Opcode.LD, Opcode.ST):
            rd = self._parse_reg(args[0])
            mem_operand = args[1]
            # Pattern: offset[rs1] or [rs1] or symbol
            match = re.match(r"^([^\[]*)\[([^\]]+)\]$", mem_operand)
            if match:
                offset_str = match.group(1).strip()
                rs1_str = match.group(2).strip()
                imm = self._parse_int(offset_str, symbol_table) if offset_str else 0
                rs1 = self._parse_reg(rs1_str)
            else:
                # Could be a direct label address or simple constant
                imm = self._parse_int(mem_operand, symbol_table)
                rs1 = 0  # relative to r0
            return encode_instruction(
                DecodedInstruction(raw=0, opcode=opcode, is_imm=True, rd=rd, rs1=rs1, imm=imm)
            )

        # 5. Move Instruction: mov rd, rs1 (Register) OR mov rd, imm (Immediate)
        if opcode == Opcode.MOV:
            rd = self._parse_reg(args[0])
            src_token = args[1]
            if src_token.lower() in REGISTER_ALIASES:
                rs1 = self._parse_reg(src_token)
                return encode_instruction(
                    DecodedInstruction(raw=0, opcode=opcode, is_imm=False, rd=rd, rs1=rs1, rs2=0)
                )
            else:
                imm = self._parse_int(src_token, symbol_table)
                return encode_instruction(
                    DecodedInstruction(raw=0, opcode=opcode, is_imm=True, rd=rd, rs1=0, imm=imm)
                )

        # 6. Not Instruction: not rd, rs1
        if opcode == Opcode.NOT:
            rd = self._parse_reg(args[0])
            rs1 = self._parse_reg(args[1])
            return encode_instruction(
                DecodedInstruction(raw=0, opcode=opcode, is_imm=False, rd=rd, rs1=rs1, rs2=0)
            )

        # 6b. Unary bit-manipulation: clz rd, rs1  |  popcnt rd, rs1
        if opcode in (Opcode.CLZ, Opcode.POPCNT):
            rd = self._parse_reg(args[0])
            rs1 = self._parse_reg(args[1])
            return encode_instruction(
                DecodedInstruction(raw=0, opcode=opcode, is_imm=False, rd=rd, rs1=rs1, rs2=0)
            )

        # 7. Comparison: cmp rs1, rs2 OR cmp rs1, imm
        if opcode == Opcode.CMP:
            rs1 = self._parse_reg(args[0])
            op2 = args[1]
            if op2.lower() in REGISTER_ALIASES:
                rs2 = self._parse_reg(op2)
                return encode_instruction(
                    DecodedInstruction(raw=0, opcode=opcode, is_imm=False, rd=0, rs1=rs1, rs2=rs2)
                )
            else:
                imm = self._parse_int(op2, symbol_table)
                return encode_instruction(
                    DecodedInstruction(raw=0, opcode=opcode, is_imm=True, rd=0, rs1=rs1, imm=imm)
                )

        # 8. Standard 3-Operand ALU: op rd, rs1, rs2 (Register) OR op rd, rs1, imm (Immediate)
        rd = self._parse_reg(args[0])
        rs1 = self._parse_reg(args[1])
        op2 = args[2]

        if op2.lower() in REGISTER_ALIASES:
            rs2 = self._parse_reg(op2)
            return encode_instruction(
                DecodedInstruction(raw=0, opcode=opcode, is_imm=False, rd=rd, rs1=rs1, rs2=rs2)
            )
        else:
            imm = self._parse_int(op2, symbol_table)
            return encode_instruction(
                DecodedInstruction(raw=0, opcode=opcode, is_imm=True, rd=rd, rs1=rs1, imm=imm)
            )
